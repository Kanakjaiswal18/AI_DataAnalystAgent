"""
chart.py
Turns a SQL result set into a visualization. Chart type is chosen
heuristically from the shape of the data (no LLM call needed for this part —
keeps it fast and deterministic):

- 1 numeric column + 1 categorical/date column -> bar chart (or line chart
  if the categorical column looks like a date/time series)
- 2+ numeric columns -> scatter plot of the first two
- single numeric column, no category -> histogram
- anything else -> no chart, just the table

Returns a base64-encoded PNG so the API stays framework-agnostic (any
frontend can just drop it into an <img src="data:image/png;base64,...">).
"""

import base64
import io
import logging
from datetime import date, datetime
from decimal import Decimal

import matplotlib
matplotlib.use("Agg")  # headless rendering — no display server needed
import matplotlib.pyplot as plt

log = logging.getLogger(__name__)

MAX_CHART_ROWS = 50  # keep bar/line charts readable


def _is_numeric(val) -> bool:
    return isinstance(val, (int, float, Decimal)) and not isinstance(val, bool)


def _is_datelike(val) -> bool:
    return isinstance(val, (date, datetime))


def _classify_columns(columns: list[str], rows: list[tuple]) -> dict:
    if not rows:
        return {"numeric": [], "categorical": [], "datelike": []}
    sample = rows[0]
    numeric, categorical, datelike = [], [], []
    for i, col in enumerate(columns):
        val = sample[i]
        if _is_datelike(val):
            datelike.append(i)
        elif _is_numeric(val):
            numeric.append(i)
        else:
            categorical.append(i)
    return {"numeric": numeric, "categorical": categorical, "datelike": datelike}


def generate_chart(columns: list[str], rows: list[tuple]) -> dict | None:
    """
    Returns {"image_base64": ..., "chart_type": ...} or None if the result
    shape isn't chartable (e.g. a single scalar, or too many free-text columns).
    """
    if not rows or not columns:
        return None

    kinds = _classify_columns(columns, rows)
    trimmed = rows[:MAX_CHART_ROWS]

    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=130)
    chart_type = None

    try:
        if kinds["datelike"] and kinds["numeric"]:
            x_idx, y_idx = kinds["datelike"][0], kinds["numeric"][0]
            xs = [r[x_idx] for r in trimmed]
            ys = [float(r[y_idx]) for r in trimmed]
            ax.plot(xs, ys, marker="o", linewidth=2, color="#2563eb")
            ax.set_xlabel(columns[x_idx])
            ax.set_ylabel(columns[y_idx])
            fig.autofmt_xdate(rotation=30)
            chart_type = "line"

        elif kinds["categorical"] and kinds["numeric"]:
            x_idx, y_idx = kinds["categorical"][0], kinds["numeric"][0]
            xs = [str(r[x_idx]) for r in trimmed]
            ys = [float(r[y_idx]) for r in trimmed]
            ax.bar(xs, ys, color="#2563eb")
            ax.set_xlabel(columns[x_idx])
            ax.set_ylabel(columns[y_idx])
            plt.xticks(rotation=45, ha="right")
            chart_type = "bar"

        elif len(kinds["numeric"]) >= 2:
            x_idx, y_idx = kinds["numeric"][0], kinds["numeric"][1]
            xs = [float(r[x_idx]) for r in trimmed]
            ys = [float(r[y_idx]) for r in trimmed]
            ax.scatter(xs, ys, color="#2563eb", alpha=0.75)
            ax.set_xlabel(columns[x_idx])
            ax.set_ylabel(columns[y_idx])
            chart_type = "scatter"

        elif len(kinds["numeric"]) == 1:
            y_idx = kinds["numeric"][0]
            ys = [float(r[y_idx]) for r in trimmed]
            ax.hist(ys, bins=min(20, max(5, len(ys) // 2)), color="#2563eb")
            ax.set_xlabel(columns[y_idx])
            ax.set_ylabel("count")
            chart_type = "histogram"

        else:
            plt.close(fig)
            return None

        ax.set_title(chart_type.capitalize() + " of query result", fontsize=11)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("ascii")
        return {"image_base64": encoded, "chart_type": chart_type}

    except Exception as e:
        log.warning(f"Chart generation failed: {e}")
        plt.close(fig)
        return None
