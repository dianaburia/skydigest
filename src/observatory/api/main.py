"""FastAPI application: browser chat over the RAG pipeline.

Thin layer per the codebase rules: no SQL, no model calls, no prompts here —
endpoints validate HTTP input, call the existing rag functions, and shape
the HTTP response.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from observatory.config import get_settings
from observatory.infra.logging_setup import setup_logging
from observatory.repository import get_issue, get_latest_issue, list_issues
from observatory.rag.answer import (
    StreamDelta,
    StreamSources,
    answer,
    answer_stream,
    cited_numbers,
)
from observatory.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)

CHAT_PAGE = Path("templates/chat.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up the embedding model at startup so the first user question
    doesn't pay the ~10s model-loading cost."""
    setup_logging()
    logger.info("Warming up the embedding model...")
    embed_texts(["warmup"])
    logger.info("Model ready, serving requests.")
    yield


class DailyIpRateLimiter:
    """In-memory per-IP daily counter for the public /ask endpoint.

    Every answered question spends real API credits, so anonymous usage is
    capped per IP per UTC day. Single-process in-memory state is enough for
    our one uvicorn worker; counts reset on redeploy, which is acceptable.
    """

    def __init__(self, limit: int):
        self.limit = limit
        self._day = date.today()
        self._counts: dict[str, int] = {}

    def allow(self, ip: str, today: date | None = None) -> bool:
        today = today or date.today()
        if today != self._day:  # new day: drop yesterday's counts entirely
            self._day = today
            self._counts = {}
        used = self._counts.get(ip, 0)
        if used >= self.limit:
            return False
        self._counts[ip] = used + 1
        return True


def _client_ip(request: Request) -> str:
    """Real client IP behind the platform proxy (first X-Forwarded-For hop)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_rate_limiter: DailyIpRateLimiter | None = None


def get_rate_limiter() -> DailyIpRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DailyIpRateLimiter(limit=get_settings().ask_daily_limit)
    return _rate_limiter


app = FastAPI(title="Skydigest", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    # Long enough for a question plus a highlighted issue passage
    # (highlight-to-ask sends both in one string).
    question: str = Field(min_length=1, max_length=1000)


class SourceOut(BaseModel):
    number: int
    title: str
    url: str
    doc_type: str  # 'article' | 'paper'


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, request: Request) -> AskResponse:
    if not get_rate_limiter().allow(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail=f"Daily question limit reached ({get_settings().ask_daily_limit}/day). Come back tomorrow!",
        )
    result = answer(payload.question)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail="Failed to generate an answer; see server logs.",
        )
    cited = cited_numbers(result["answer"])
    sources = [
        SourceOut(number=s.number, title=s.title, url=s.url, doc_type=s.doc_type)
        for s in result["sources"]
        if s.number in cited
    ]
    return AskResponse(answer=result["answer"], sources=sources)


@app.post("/ask/stream")
def ask_stream(payload: AskRequest, request: Request) -> StreamingResponse:
    """Streaming variant of /ask: Server-Sent Events with the answer text
    arriving in pieces, then the cited sources, then a done marker."""
    if not get_rate_limiter().allow(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail=f"Daily question limit reached ({get_settings().ask_daily_limit}/day). Come back tomorrow!",
        )

    def sse_events() -> Iterator[str]:
        for event in answer_stream(payload.question):
            if isinstance(event, StreamDelta):
                data = {"type": "delta", "text": event.text}
            elif isinstance(event, StreamSources):
                data = {
                    "type": "sources",
                    "sources": [
                        SourceOut(
                            number=s.number, title=s.title, url=s.url, doc_type=s.doc_type
                        ).model_dump()
                        for s in event.sources
                    ],
                }
            else:  # StreamError
                data = {"type": "error", "detail": event.detail}
            yield f"data: {json.dumps(data)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        sse_events(),
        media_type="text/event-stream",
        # Ask proxies not to buffer, so pieces reach the browser immediately.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class IssueSummaryOut(BaseModel):
    issue_date: date
    title: str


class IssueOut(BaseModel):
    issue_date: date
    title: str
    html: str


@app.get("/issues", response_model=list[IssueSummaryOut])
def issues() -> list[IssueSummaryOut]:
    """All issues, newest first (metadata only, no html)."""
    return [
        IssueSummaryOut(issue_date=i.issue_date, title=i.title) for i in list_issues()
    ]


@app.get("/issues/{issue_date}", response_model=IssueOut)
def issue_by_date(issue_date: date) -> IssueOut:
    """One issue by date (YYYY-MM-DD), including its rendered html."""
    issue = get_issue(issue_date)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"No issue for {issue_date}.")
    return IssueOut(issue_date=issue.issue_date, title=issue.title, html=issue.html)


NO_ISSUE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Skydigest</title></head>
<body style="font-family: Georgia, serif; text-align: center; padding-top: 4rem;">
<h1>Skydigest</h1>
<p>The first weekly issue hasn't been generated yet — check back on Saturday.</p>
<p><a href="/chat">Meanwhile, ask the archive anything →</a></p>
</body></html>"""


@app.get("/")
def index() -> HTMLResponse:
    """The latest journal issue is the front page."""
    issue = get_latest_issue()
    if issue is None:
        return HTMLResponse(NO_ISSUE_PAGE)
    return HTMLResponse(issue.html)


@app.get("/chat")
def chat() -> FileResponse:
    return FileResponse(CHAT_PAGE)
