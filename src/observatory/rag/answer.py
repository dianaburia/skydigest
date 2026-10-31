"""RAG answering: question in, grounded answer out.

The agent graph (rag/agent.py) prepares the context: routes the question to
vector search over the archive or to SQL over space_weather, reformulating
weak queries once. This module turns that context into the final answer —
archive answers cite numbered sources, weather answers report measurements —
with explicit permission to say "I don't know" when sources don't cover it.
"""

import logging
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

from observatory.config import get_settings
from observatory.infra.logging_setup import setup_logging
from observatory.rag.agent import prepare
from observatory.repository import (
    AskedQuestion,
    RetrievedChunk,
    SpaceWeatherStat,
    insert_asked_question,
)

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """\
You are a science communicator answering questions about astronomy and space.
Plain English, short sentences, no jargon (or jargon explained in passing).
You answer ONLY from the numbered sources provided, citing them by number
like [1]. If the sources do not contain the answer, say plainly "I don't know
based on my sources" — never fabricate or answer from general knowledge."""


@dataclass
class GroupedSource:
    number: int
    doc_type: str  # 'article' | 'paper'
    doc_id: str
    title: str
    url: str
    best_score: float  # cosine distance of this document's closest chunk
    contents: list[str] = field(default_factory=list)


def group_sources(chunks: list[RetrievedChunk]) -> list[GroupedSource]:
    """Group retrieved chunks by owning document, one source number each.

    Chunks arrive sorted by score (best first), so a document's number
    reflects the rank of its best chunk.
    """
    by_doc: dict[tuple[str, str], GroupedSource] = {}
    for chunk in chunks:
        key = (chunk.doc_type, chunk.doc_id)
        if key not in by_doc:
            by_doc[key] = GroupedSource(
                number=len(by_doc) + 1,
                doc_type=chunk.doc_type,
                doc_id=chunk.doc_id,
                title=chunk.title,
                url=chunk.url,
                best_score=chunk.score,
            )
        by_doc[key].contents.append(chunk.content)
    return list(by_doc.values())


def build_prompt(question: str, sources: list[GroupedSource]) -> str:
    blocks = []
    for s in sources:
        texts = "\n".join(f"    {content}" for content in s.contents)
        blocks.append(f"[{s.number}] {s.title} ({s.doc_type})\n{texts}")
    sources_block = "\n\n".join(blocks)
    return f"""\
=== SOURCES ===
{sources_block}

=== QUESTION ===
{question}

Answer the question using ONLY the sources above. Cite source numbers inline
like [1]. If the sources do not answer the question, say so honestly."""


WEATHER_SYSTEM_PROMPT = """\
You are a science communicator reporting current space weather conditions.
Plain English, short sentences, jargon explained in passing. Answer ONLY from
the measurements provided — never estimate or recall other values. Mention
that the measurements come from NOAA SWPC real-time data."""

_METRIC_LABELS = {
    "kp": ("Kp index (planetary geomagnetic activity, 0-9 scale; 5+ = storm)", ""),
    "sw_speed": ("solar wind speed", "km/s"),
    "sw_density": ("solar wind proton density", "protons/cm3"),
    "bz": ("IMF Bz, north-south magnetic field (negative = geoeffective)", "nT"),
}


def build_weather_prompt(question: str, stats: list[SpaceWeatherStat]) -> str:
    lines = []
    for s in stats:
        label, unit = _METRIC_LABELS.get(s.metric, (s.metric, ""))
        unit_sfx = f" {unit}" if unit else ""
        lines.append(
            f"- {label}: latest {s.latest:g}{unit_sfx}"
            f" (measured {s.latest_ts:%Y-%m-%d %H:%M} UTC);"
            f" last 7 days: min {s.minimum:g}, max {s.maximum:g}{unit_sfx}"
        )
    measurements = "\n".join(lines)
    return f"""\
=== MEASUREMENTS (NOAA SWPC via our space_weather table) ===
{measurements}

=== QUESTION ===
{question}

Answer the question using ONLY the measurements above."""


def _log_question(question: str, chunks: list[RetrievedChunk]) -> None:
    """Best-effort append to the asked_questions log.

    The log is eval-set raw material, never worth failing an answer over:
    any error is reported and swallowed.
    """
    try:
        insert_asked_question(AskedQuestion(question=question, retrieved=chunks))
    except Exception:
        logger.warning("Failed to log the asked question", exc_info=True)


@dataclass
class _Generation:
    """Everything the LLM needs to produce the final answer."""

    system: str
    prompt: str
    sources: list[GroupedSource]


def _prepare_generation(question: str, log: bool) -> _Generation | None:
    """Run the agent graph and turn its context into a generation request."""
    prepared = prepare(question)
    if log:
        _log_question(question, prepared.chunks)

    if prepared.route == "weather":
        if not prepared.weather:
            logger.error("Weather route chosen but space_weather returned no rows")
            return None
        return _Generation(
            system=WEATHER_SYSTEM_PROMPT,
            prompt=build_weather_prompt(question, prepared.weather),
            sources=[],
        )

    if not prepared.chunks:
        logger.error("Retrieval returned no chunks — is the index empty?")
        return None
    sources = group_sources(prepared.chunks)
    logger.info(
        "Question retrieved %d chunks across %d documents (best score %.3f)%s",
        len(prepared.chunks),
        len(sources),
        sources[0].best_score,
        " after reformulation" if prepared.reformulated else "",
    )
    return _Generation(
        system=SYSTEM_PROMPT,
        prompt=build_prompt(question, sources),
        sources=sources,
    )


def answer(question: str, log: bool = True) -> dict | None:
    """Answer a question via the agent graph (vector search or SQL route).

    Returns {"answer": str, "sources": list[GroupedSource]} or None on failure.
    Weather-route answers carry no sources — the numbers ARE the answer.
    log=False skips the asked_questions log — used by the eval runner so
    synthetic eval runs don't pollute the real-question log.
    """
    generation = _prepare_generation(question, log)
    if generation is None:
        return None

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=generation.system,
            messages=[{"role": "user", "content": generation.prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed: %s", e)
        return None

    return {"answer": response.content[0].text, "sources": generation.sources}


@dataclass
class StreamDelta:
    """A piece of answer text, emitted as the model generates it."""

    text: str


@dataclass
class StreamSources:
    """Final event of a successful stream: the sources the answer cited."""

    sources: list[GroupedSource]


@dataclass
class StreamError:
    """Terminal event when retrieval or generation failed."""

    detail: str


StreamEvent = StreamDelta | StreamSources | StreamError


def answer_stream(question: str) -> Iterator[StreamEvent]:
    """Same chain as answer(), but yields the answer text incrementally.

    Yields StreamDelta events while the model generates, then one
    StreamSources with the cited sources; StreamError is terminal.
    """
    generation = _prepare_generation(question, log=True)
    if generation is None:
        yield StreamError(detail="The archive returned nothing; try again later.")
        return

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    parts: list[str] = []
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=generation.system,
            messages=[{"role": "user", "content": generation.prompt}],
        ) as stream:
            for text in stream.text_stream:
                parts.append(text)
                yield StreamDelta(text=text)
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed: %s", e)
        yield StreamError(detail="Failed to generate an answer; try again later.")
        return

    cited = cited_numbers("".join(parts))
    yield StreamSources(sources=[s for s in generation.sources if s.number in cited])


def cited_numbers(answer_text: str) -> set[int]:
    """Source numbers actually cited in an answer, e.g. {1, 3} from '[1] ... [3]'."""
    return {int(n) for n in re.findall(r"\[(\d+)\]", answer_text)}


def main() -> int:
    setup_logging()
    if len(sys.argv) < 2:
        print('Usage: python -m observatory.rag.answer "your question"', file=sys.stderr)
        return 1
    question = sys.argv[1]

    result = answer(question)
    if result is None:
        print("Failed to answer (see errors above).", file=sys.stderr)
        return 1

    print()
    print(result["answer"])
    print()
    cited = cited_numbers(result["answer"])
    if cited:
        print("Sources:")
        for s in result["sources"]:
            if s.number in cited:
                print(f"  [{s.number}] {s.title}\n      {s.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
