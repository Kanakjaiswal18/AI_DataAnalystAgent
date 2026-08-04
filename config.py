"""
config.py
Central configuration for the AI Data Analyst Agent.

All values are read from environment variables (with sane defaults for local
dev) so the service can be deployed without code changes — swap Postgres
credentials, LLM provider, or safety limits purely through .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM provider ───────────────────────────────────────────────────────────
# Works with any OpenAI-compatible endpoint (OpenAI, Azure OpenAI, local
# vLLM/Ollama gateway, etc.) — just point OPENAI_BASE_URL elsewhere.
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL  = os.getenv("OPENAI_BASE_URL")  # None -> official OpenAI endpoint
SQL_MODEL        = os.getenv("SQL_MODEL", "gpt-4o-mini")
INSIGHT_MODEL    = os.getenv("INSIGHT_MODEL", "gpt-4o-mini")

# ── PostgreSQL ─────────────────────────────────────────────────────────────
PG_HOST     = os.getenv("PG_HOST", "localhost")
PG_PORT     = int(os.getenv("PG_PORT", 5432))
PG_DB       = os.getenv("PG_DB", "analyst_demo")
PG_USER     = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

# ── Agent safety limits ────────────────────────────────────────────────────
MAX_SQL_RETRIES     = int(os.getenv("MAX_SQL_RETRIES", 2))     # self-correction attempts
MAX_ROWS_RETURNED   = int(os.getenv("MAX_ROWS_RETURNED", 500)) # hard cap injected into every query
QUERY_TIMEOUT_MS    = int(os.getenv("QUERY_TIMEOUT_MS", 5000)) # statement_timeout per query

# Only these statement types are ever allowed to execute. Everything else
# (INSERT/UPDATE/DELETE/DROP/ALTER/GRANT/...) is rejected before it reaches
# the database — see app/sql_guard.py.
ALLOWED_STATEMENT_PREFIXES = ("select", "with")

API_KEY = os.getenv("APP_API_KEY", "")  # optional shared-secret auth for /chat
