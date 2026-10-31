"""Agentic retrieval on LangGraph: route, retrieve, reformulate when weak.

The graph prepares CONTEXT for an answer; the answer itself (including
streaming) stays in rag/answer.py, which consumes the Prepared result:

    route                 one cheap LLM call: 'weather' or 'archive'
      ├─ weather          numbers from the space_weather table (repository
      │                   SQL — measurements are never indexed as text, so
      │                   vector search cannot answer "what was Kp today?")
      └─ archive          vector retrieve -> if the best cosine distance is
                          in the weak zone, reformulate the query once (LLM)
                          and retrieve again; keep the better attempt.

Thresholds come from observed bge-m3 score bands on our corpus (EVAL.md):
<0.35 confident, 0.35-0.45 on-topic, >0.45 weak.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from observatory.config import get_settings
from observatory.rag.retrieve import retrieve
from observatory.repository import (
    RetrievedChunk,
    SpaceWeatherStat,
    get_space_weather_stats,
)

logger = logging.getLogger(__name__)

ROUTER_MODEL = "claude-sonnet-4-6"
TOP_K = 8
WEAK_SCORE = 0.45  # cosine distance above this = weak zone (see EVAL.md bands)
WEATHER_WINDOW_DAYS = 7

ROUTER_PROMPT = """\
Classify the user's question for an astronomy site that has two data sources:
- "weather": numeric space-weather MEASUREMENTS (Kp index, solar wind speed or
  density, Bz magnetic field) — current values or recent extremes. Only route
  here when the user asks about the conditions/values themselves.
- "archive": everything else — news, papers, missions, explanations, including
  questions ABOUT space weather science (what causes auroras, how CMEs work).

Reply with JSON only: {"route": "weather"} or {"route": "archive"}

Question:
"""

REFORMULATE_PROMPT = """\
A semantic search over astronomy news and papers returned only weak matches
for the query below. Rewrite it as a better search query: expand abbreviations,
add the likely scientific terms, drop filler words. Keep the original meaning.
Reply with the rewritten query only, no quotes, no explanations.

Query:
"""


@dataclass
class Prepared:
    """What the graph hands to the answer generator."""

    route: Literal["weather", "archive"]
    chunks: list[RetrievedChunk] = field(default_factory=list)
    weather: list[SpaceWeatherStat] = field(default_factory=list)
    search_query: str = ""  # the query that produced `chunks` (may be rewritten)
    reformulated: bool = False


class _State(TypedDict, total=False):
    question: str
    route: str
    search_query: str
    chunks: list[RetrievedChunk]
    weather: list[SpaceWeatherStat]
    reformulated: bool


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _best_score(chunks: list[RetrievedChunk]) -> float:
    return chunks[0].score if chunks else float("inf")


def needs_reformulation(chunks: list[RetrievedChunk], reformulated: bool) -> bool:
    """One retry, and only when the whole top-K sits in the weak zone."""
    return not reformulated and _best_score(chunks) > WEAK_SCORE


def _route_node(state: _State) -> _State:
    try:
        response = _client().messages.create(
            model=ROUTER_MODEL,
            max_tokens=16,
            messages=[{"role": "user", "content": ROUTER_PROMPT + state["question"]}],
        )
        match = re.search(r'"route"\s*:\s*"(weather|archive)"', response.content[0].text)
        route = match.group(1) if match else "archive"
    except anthropic.APIError as e:
        logger.warning("Router call failed (%s), defaulting to archive", e)
        route = "archive"
    logger.info("Agent routed question to: %s", route)
    return {"route": route}


def _weather_node(state: _State) -> _State:
    return {"weather": get_space_weather_stats(WEATHER_WINDOW_DAYS)}


def _retrieve_node(state: _State) -> _State:
    query = state.get("search_query") or state["question"]
    chunks = retrieve(query, top_k=TOP_K)
    # Keep the better of the two attempts: a rewrite that made things
    # worse must not replace the original results.
    previous = state.get("chunks")
    if previous and _best_score(previous) <= _best_score(chunks):
        return {"chunks": previous, "search_query": state["question"]}
    return {"chunks": chunks, "search_query": query}


def _reformulate_node(state: _State) -> _State:
    try:
        response = _client().messages.create(
            model=ROUTER_MODEL,
            max_tokens=128,
            messages=[
                {"role": "user", "content": REFORMULATE_PROMPT + state["question"]}
            ],
        )
        rewritten = response.content[0].text.strip()
    except anthropic.APIError as e:
        logger.warning("Reformulation call failed (%s), keeping original query", e)
        rewritten = state["question"]
    logger.info("Agent reformulated weak query to: %s", rewritten[:120])
    return {"search_query": rewritten, "reformulated": True}


def _after_route(state: _State) -> str:
    return state["route"]


def _after_retrieve(state: _State) -> str:
    if needs_reformulation(state["chunks"], state.get("reformulated", False)):
        return "reformulate"
    return "done"


def build_graph():
    graph = StateGraph(_State)
    graph.add_node("route", _route_node)
    graph.add_node("fetch_weather", _weather_node)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("reformulate", _reformulate_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route", _after_route, {"weather": "fetch_weather", "archive": "retrieve"}
    )
    graph.add_edge("fetch_weather", END)
    graph.add_conditional_edges(
        "retrieve", _after_retrieve, {"reformulate": "reformulate", "done": END}
    )
    graph.add_edge("reformulate", "retrieve")
    return graph.compile()


_graph = None


def prepare(question: str) -> Prepared:
    """Run the agent graph and return the prepared answering context."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    state = _graph.invoke({"question": question})
    return Prepared(
        route=state["route"],
        chunks=state.get("chunks", []),
        weather=state.get("weather", []),
        search_query=state.get("search_query", question),
        reformulated=state.get("reformulated", False),
    )
