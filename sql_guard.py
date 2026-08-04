"""
sql_guard.py
Safety layer between "SQL the LLM wrote" and "SQL that touches the database."

This is the most important file in the project from a design-review
standpoint: an LLM-generated-SQL agent is only as safe as its guardrail.
Rules enforced here:

1. Exactly one statement (no semicolon-separated statement stacking).
2. Statement must start with SELECT or a read-only WITH ... SELECT CTE.
3. Blocklist of destructive/DDL/DCL keywords, checked even inside CTEs and
   subqueries (defense in depth beyond the prefix check).
4. No SQL comments (-- or /* */) — a common vector for smuggling extra
   clauses past naive validation.
5. A LIMIT clause is injected if the LLM didn't include one, capped at
   MAX_ROWS_RETURNED regardless of what the LLM requested.
"""

import re
from dataclasses import dataclass

from config import ALLOWED_STATEMENT_PREFIXES, MAX_ROWS_RETURNED

BLOCKED_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate", "grant",
    "revoke", "create", "replace", "copy", "vacuum", "call", "execute",
    "do", "commit", "rollback", "set ", "listen", "notify", "lock",
    "into", "merge",
]

COMMENT_RE = re.compile(r"(--|/\*)")
LIMIT_RE   = re.compile(r"\blimit\s+\d+\b", re.I)


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""
    error: str = ""


def validate_and_cap(raw_sql: str) -> ValidationResult:
    sql = (raw_sql or "").strip().rstrip(";").strip()

    if not sql:
        return ValidationResult(ok=False, error="Empty SQL.")

    if ";" in sql:
        return ValidationResult(ok=False, error="Multiple statements are not allowed.")

    if COMMENT_RE.search(sql):
        return ValidationResult(ok=False, error="SQL comments are not allowed.")

    lowered = sql.lower()

    if not lowered.startswith(ALLOWED_STATEMENT_PREFIXES):
        return ValidationResult(
            ok=False,
            error="Only read-only SELECT (or WITH ... SELECT) statements are allowed."
        )

    for kw in BLOCKED_KEYWORDS:
        # word-boundary match so e.g. "insert" doesn't false-positive on
        # a column literally named "inserted_at" — check for the keyword
        # as a standalone token.
        if re.search(rf"\b{re.escape(kw.strip())}\b", lowered):
            return ValidationResult(ok=False, error=f"Disallowed keyword detected: '{kw.strip()}'.")

    if not LIMIT_RE.search(lowered):
        sql = f"{sql}\nLIMIT {MAX_ROWS_RETURNED}"
    else:
        # Cap whatever LIMIT the LLM specified to our hard maximum.
        def _cap(match: re.Match) -> str:
            n = int(re.search(r"\d+", match.group(0)).group(0))
            return f"LIMIT {min(n, MAX_ROWS_RETURNED)}"
        sql = LIMIT_RE.sub(_cap, sql, count=1)

    return ValidationResult(ok=True, sql=sql)
