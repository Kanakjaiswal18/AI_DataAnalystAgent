"""
main.py
FastAPI backend for the AI Data Analyst Agent.

Run with:
    python -m uvicorn main:app --host 0.0.0.0 --port 8000

Endpoints:
    POST /chat    — natural language question -> SQL + insight + chart
    GET  /schema  — current database schema (debugging / transparency)
    GET  /health  — service + DB connectivity check
"""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import API_KEY
from db import init_pool, get_schema_text
from graph import run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up — connecting to PostgreSQL…")
    init_pool()
    try:
        get_schema_text(force_refresh=True)
        log.info("Schema loaded successfully.")
    except Exception as e:
        log.error(f"Could not load schema at startup: {e}")
    yield
    log.info("Shutting down.")


app = FastAPI(title="AI Data Analyst Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: List[ChatMessage] = []


def check_auth(request: Request):
    if API_KEY:
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    try:
        schema = get_schema_text()
        return {"status": "ok", "schema_loaded": bool(schema)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/schema")
def schema(request: Request):
    check_auth(request)
    return {"schema": get_schema_text()}


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    check_auth(request)

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    history = [{"role": m.role, "content": m.content} for m in req.history[-6:]]

    try:
        result = run_agent(question, history=history)
    except Exception as e:
        log.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    if result.get("failed"):
        return {
            "type": "error",
            "message": result.get("failure_reason", "The agent could not answer this question."),
            "sql": result.get("sql", ""),
        }

    columns = result.get("columns", [])
    rows = result.get("rows", [])
    # JSON-serialize row values that aren't natively serializable (Decimal, date, etc.)
    def _serialize(v):
        try:
            import json
            json.dumps(v)
            return v
        except TypeError:
            return str(v)

    serialized_rows = [[_serialize(v) for v in row] for row in rows]

    return {
        "type": "result",
        "sql": result.get("sql", ""),
        "columns": columns,
        "rows": serialized_rows,
        "row_count": len(rows),
        "insight": result.get("insight", ""),
        "chart": result.get("chart"),
    }


app.mount("/", StaticFiles(directory=".", html=True), name="static")
