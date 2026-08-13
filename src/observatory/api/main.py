"""FastAPI application: browser chat over the RAG pipeline.

Thin layer per the codebase rules: no SQL, no model calls, no prompts here —
endpoints validate HTTP input, call the existing rag functions, and shape
the HTTP response.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from observatory.infra.logging_setup import setup_logging
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(CHAT_PAGE)
