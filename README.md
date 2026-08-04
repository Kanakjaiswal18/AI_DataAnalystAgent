# AI_DataAnalystAgent
# AI Data Analyst Agent

Converts natural-language questions into SQL, executes them against
PostgreSQL, and returns a plain-English insight plus an auto-generated
chart — with a LangGraph-orchestrated self-correction loop and a hard
safety layer that guarantees only read-only queries ever reach the database.

## Architecture

```
User question
     │
     ▼
┌─────────────────┐
│  generate_sql    │  LLM writes SQL against live-introspected schema
└────────┬─────────┘
         ▼
┌─────────────────┐     invalid SQL (blocked keyword,
│  validate_sql    │────multi-statement, no SELECT)────┐
└────────┬─────────┘                                    │
         │ valid                                        │
         ▼                                               │
┌─────────────────┐     DB execution error               │
│  execute_sql     │────(bad column, syntax, etc.)───────┤
└────────┬─────────┘                                    │
         │ success                          retry, up to │
         ▼                                MAX_SQL_RETRIES │
┌─────────────────┐                                      │
│ generate_insight │  ◄────────────────────────────────────┘ (loops back
└────────┬─────────┘                                       to generate_sql
         ▼                                                  with the error
┌─────────────────┐                                         fed back in)
│  generate_chart  │  heuristic chart-type selection, matplotlib -> base64
└────────┬─────────┘
         ▼
     JSON response
```

This is a genuine self-correcting agent, not a single prompt-and-pray call:
if the LLM writes SQL referencing a nonexistent column, or the query times
out, the actual database/validation error is fed back to the model and it
gets another attempt (bounded, so it can't loop forever).

## Why the safety layer matters

Letting an LLM write and execute arbitrary SQL is dangerous by default.
`app/sql_guard.py` is the guardrail:
- Single-statement only (blocks `; DROP TABLE ...` injection via statement stacking)
- Must start with `SELECT` or a read-only `WITH ... SELECT` CTE
- Blocklist of DML/DDL/DCL keywords, checked as whole tokens (not naive substring match)
- SQL comments stripped/rejected (a common vector for smuggling extra clauses)
- Every query gets a hard `LIMIT` cap regardless of what the LLM wrote, and a
  `statement_timeout` regardless of query complexity

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY and Postgres credentials

# create + seed a demo database (customers/products/orders/order_items)
createdb analyst_demo
python seed_db.py

# run the API + demo UI
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` for the demo chat UI, or call the API directly:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top 5 products by revenue?"}'
```

## Project structure

```
app/
  config.py     — env-driven settings (LLM provider, DB, safety limits)
  db.py         — connection pool + live schema introspection
  sql_guard.py  — SQL safety validation (the guardrail)
  chart.py      — result-shape -> chart-type heuristic, matplotlib rendering
  graph.py      — LangGraph state machine (the agent itself)
  main.py       — FastAPI app (/chat, /schema, /health)
seed_db.py      — synthetic e-commerce dataset for demoing
static/index.html — minimal chat UI
```

## Extending it

- Swap the demo e-commerce schema for a real one — `get_schema_text()` in
  `db.py` introspects `information_schema` at runtime, so no code changes
  are needed for a different database.
- Multi-turn follow-ups ("now break that down by month") already work —
  the last few conversation turns are passed to `generate_sql` as context.
- To support multiple chart libraries on the frontend instead of a static
  PNG, swap `chart.py` to return structured `{x, y, type}` data instead of
  a rendered image, and let the frontend use Chart.js/Recharts/Plotly.
