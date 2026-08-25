"""FastAPI application: browser chat over the RAG pipeline.

Thin layer per the codebase rules: no SQL, no model calls, no prompts here —
endpoints validate HTTP input, call the existing rag functions, and shape
the HTTP response.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from observatory.infra.logging_setup import setup_logging
from observatory.repository import get_latest_issue
from observatory.rag.answer import answer, cited_numbers
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


app = FastAPI(title="Observatory", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


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
def ask(request: AskRequest) -> AskResponse:
    result = answer(request.question)
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


NO_ISSUE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Observatory</title></head>
<body style="font-family: Georgia, serif; text-align: center; padding-top: 4rem;">
<h1>Observatory</h1>
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
