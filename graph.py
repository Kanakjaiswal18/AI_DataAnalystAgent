"""
graph.py
The LangGraph state machine that turns a natural-language question into a
validated SQL query, a result set, a plain-English insight, and a chart.

Graph shape:

    generate_sql --> validate_sql --(invalid)--> generate_sql   [retry loop]
                          |
                       (valid)
                          v
                     execute_sql --(db error)--> generate_sql   [self-correct]
                          |
                       (success)
                          v
                   generate_insight --> generate_chart --> END

Both retry loops are bounded by MAX_SQL_RETRIES. If the agent still can't
produce a working query after that many attempts, it returns a clear,
honest failure message instead of a hallucinated answer.
"""

import logging
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from openai import OpenAI

from config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, SQL_MODEL, INSIGHT_MODEL, MAX_SQL_RETRIES,
)
from db import get_schema_text, run_select
from sql_guard import validate_and_cap
from chart import generate_chart

log = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_llm() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _client


class AgentState(TypedDict, total=False):
    question: str
    history: list          # [{"role": "user"/"assistant", "content": str}, ...]
    schema_text: str
    sql: str
    error: str              # most recent validation or execution error, fed back to the LLM
    retries: int
    columns: list
    rows: list
    insight: str
    chart: Optional[dict]
    failed: bool
    failure_reason: str


SQL_SYSTEM_PROMPT = """You are a PostgreSQL query generator for an analytics agent.

Rules:
- Output ONLY the SQL query. No markdown fences, no explanation, no comments.
- Only ever write a single SELECT statement (or a WITH ... SELECT CTE). Never
  write INSERT/UPDATE/DELETE/DDL of any kind — you are read-only.
- Only reference tables and columns that appear in the provided schema.
- If the question is ambiguous, make the most reasonable assumption and
  proceed rather than asking a clarifying question — there is no user
  present to answer follow-ups.
- Prefer aggregate queries (GROUP BY, COUNT, SUM, AVG) when the question
  asks for trends, totals, or comparisons rather than raw row dumps.
- Include a reasonable ORDER BY for anything time-based or ranked.
"""

INSIGHT_SYSTEM_PROMPT = """You are a data analyst explaining a SQL query result to a
non-technical stakeholder.

Rules:
- 2-4 sentences. Plain English, no jargon.
- Lead with the headline finding (the number or trend that matters most).
- Mention 1-2 supporting specifics from the actual data (real values from
  the result set only — never invent numbers not present in the rows).
- If the result set is empty, say so plainly and suggest a reason why
  (e.g. no matching records, filters too narrow) rather than fabricating
  a finding.
"""


def node_generate_sql(state: AgentState) -> AgentState:
    client = get_llm()
    schema_text = state.get("schema_text") or get_schema_text()

    user_content = f"SCHEMA:\n{schema_text}\n\nQUESTION: {state['question']}"
    if state.get("error"):
        user_content += (
            f"\n\nYour previous query failed with this error:\n{state['error']}\n"
            f"Previous query was:\n{state.get('sql', '')}\n"
            f"Fix the query and try again."
        )

    messages = [{"role": "system", "content": SQL_SYSTEM_PROMPT}]
    # Include recent conversation turns so follow-up questions like
    # "now break that down by month" resolve against prior context.
    for turn in (state.get("history") or [])[-4:]:
        messages.append(turn)
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=SQL_MODEL, messages=messages, temperature=0.0, max_tokens=500,
    )
    raw_sql = response.choices[0].message.content.strip()
    raw_sql = raw_sql.strip("`")
    if raw_sql.lower().startswith("sql"):
        raw_sql = raw_sql[3:].strip()

    return {**state, "sql": raw_sql, "schema_text": schema_text}


def node_validate_sql(state: AgentState) -> AgentState:
    result = validate_and_cap(state["sql"])
    if not result.ok:
        retries = state.get("retries", 0) + 1
        return {**state, "error": result.error, "retries": retries}
    return {**state, "sql": result.sql, "error": ""}


def node_execute_sql(state: AgentState) -> AgentState:
    try:
        columns, rows = run_select(state["sql"], max_rows=500)
        return {**state, "columns": columns, "rows": rows, "error": ""}
    except Exception as e:
        retries = state.get("retries", 0) + 1
        return {**state, "error": str(e), "retries": retries}


def node_generate_insight(state: AgentState) -> AgentState:
    client = get_llm()
    columns = state.get("columns", [])
    rows = state.get("rows", [])

    preview_rows = rows[:20]
    table_preview = "\n".join(
        ", ".join(str(v) for v in r) for r in preview_rows
    ) or "(no rows returned)"

    user_content = (
        f"QUESTION: {state['question']}\n"
        f"SQL EXECUTED: {state['sql']}\n"
        f"COLUMNS: {', '.join(columns)}\n"
        f"RESULT ROWS ({len(rows)} total, showing up to 20):\n{table_preview}"
    )

    response = client.chat.completions.create(
        model=INSIGHT_MODEL,
        messages=[
            {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2, max_tokens=300,
    )
    insight = response.choices[0].message.content.strip()
    return {**state, "insight": insight}


def node_generate_chart(state: AgentState) -> AgentState:
    chart = generate_chart(state.get("columns", []), state.get("rows", []))
    return {**state, "chart": chart}


def node_give_up(state: AgentState) -> AgentState:
    return {
        **state,
        "failed": True,
        "failure_reason": (
            f"I couldn't produce a working query after {state.get('retries', 0)} attempts. "
            f"Last error: {state.get('error', 'unknown')}"
        ),
    }


def route_after_validate(state: AgentState) -> str:
    if state.get("error"):
        if state.get("retries", 0) >= MAX_SQL_RETRIES:
            return "give_up"
        return "generate_sql"
    return "execute_sql"


def route_after_execute(state: AgentState) -> str:
    if state.get("error"):
        if state.get("retries", 0) >= MAX_SQL_RETRIES:
            return "give_up"
        return "generate_sql"
    return "generate_insight"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("generate_sql", node_generate_sql)
    graph.add_node("validate_sql", node_validate_sql)
    graph.add_node("execute_sql", node_execute_sql)
    graph.add_node("generate_insight", node_generate_insight)
    graph.add_node("generate_chart", node_generate_chart)
    graph.add_node("give_up", node_give_up)

    graph.set_entry_point("generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges("validate_sql", route_after_validate, {
        "generate_sql": "generate_sql",
        "execute_sql": "execute_sql",
        "give_up": "give_up",
    })
    graph.add_conditional_edges("execute_sql", route_after_execute, {
        "generate_sql": "generate_sql",
        "generate_insight": "generate_insight",
        "give_up": "give_up",
    })
    graph.add_edge("generate_insight", "generate_chart")
    graph.add_edge("generate_chart", END)
    graph.add_edge("give_up", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent(question: str, history: list | None = None) -> AgentState:
    graph = get_graph()
    initial: AgentState = {
        "question": question,
        "history": history or [],
        "retries": 0,
    }
    final_state = graph.invoke(initial)
    return final_state
