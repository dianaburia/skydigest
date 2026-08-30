"""RAG answering: question in, grounded answer with numbered sources out.

Chain: retrieve top chunks -> group chunks by owning document (one document =
one source number, even if several of its chunks were retrieved) -> ask Claude
to answer ONLY from those sources, citing by number, with explicit permission
to say "I don't know" when the sources don't cover the question.
"""

import logging
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic

from observatory.config import get_settings
from observatory.infra.logging_setup import setup_logging
from observatory.rag.retrieve import retrieve
from observatory.repository import RetrievedChunk

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
TOP_K = 8

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


def answer(question: str) -> dict | None:
    """Answer a question from the indexed corpus.

    Returns {"answer": str, "sources": list[GroupedSource]} or None on failure.
    """
    chunks = retrieve(question, top_k=TOP_K)
    if not chunks:
        logger.error("Retrieval returned no chunks — is the index empty?")
        return None
    sources = group_sources(chunks)
    logger.info(
        "Question retrieved %d chunks across %d documents (best score %.3f)",
        len(chunks),
        len(sources),
        sources[0].best_score,
    )

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(question, sources)}],
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed: %s", e)
        return None

    return {"answer": response.content[0].text, "sources": sources}


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
    chunks = retrieve(question, top_k=TOP_K)
    if not chunks:
        logger.error("Retrieval returned no chunks — is the index empty?")
        yield StreamError(detail="The archive returned nothing; try again later.")
        return
    sources = group_sources(chunks)
    logger.info(
        "Question retrieved %d chunks across %d documents (best score %.3f)",
        len(chunks),
        len(sources),
        sources[0].best_score,
    )

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    parts: list[str] = []
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(question, sources)}],
        ) as stream:
            for text in stream.text_stream:
                parts.append(text)
                yield StreamDelta(text=text)
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed: %s", e)
        yield StreamError(detail="Failed to generate an answer; try again later.")
        return

    cited = cited_numbers("".join(parts))
    yield StreamSources(sources=[s for s in sources if s.number in cited])


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
