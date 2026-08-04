# AI Data Analyst Agent

An AI-powered analytics assistant that converts natural language questions into SQL queries, executes them against PostgreSQL, and returns business insights with automatic visualizations.

The system uses a LangGraph-orchestrated workflow with schema-aware SQL generation, SQL validation guardrails, execution error recovery, and automated insight generation.

---

# Architecture

```
User Question
      │
      ▼
┌──────────────────┐
│  Generate SQL    │
│  (LLM + Schema)  │
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Validate SQL    │
│  Safety Layer    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Execute Query    │
│ PostgreSQL       │
└────────┬─────────┘
         │
         │ SQL error
         ▼
┌──────────────────┐
│ Retry Workflow   │
│ Error Feedback   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Generate Insight │
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Generate Chart   │
└────────┬─────────┘
         ▼
    JSON Response
```

The agent does not rely on hardcoded database knowledge. Before generating SQL, it dynamically retrieves the PostgreSQL schema and provides the available tables, columns, and relationships to the LLM.

If the generated SQL fails validation or database execution, the error is fed back into the LangGraph workflow and the model attempts correction within a bounded retry limit.

---

# Key Features

## Natural Language → SQL

Users can ask business questions such as:

```
What are the top 5 products by revenue?
```

or:

```
What was total revenue by month in 2025?
```

The agent generates the required SQL automatically.

---

## Schema-Aware SQL Generation

The system dynamically inspects the PostgreSQL database schema using `information_schema`.

The LLM receives:

- Available tables
- Column names
- Data types
- Foreign key relationships

This improves SQL generation reliability without manually defining database context.

---

## SQL Safety Guardrails

The SQL validation layer ensures only safe analytical queries reach the database.

Implemented protections:

- Allows only read-only queries
- Blocks INSERT, UPDATE, DELETE, DROP, ALTER, and other unsafe operations
- Rejects multi-statement SQL execution
- Validates SELECT and WITH queries
- Removes SQL comments
- Applies query timeout limits
- Restricts maximum returned rows

---

## Self-Correcting Agent Workflow

The LangGraph workflow handles failures automatically.

Example:

```
LLM generates SQL
        ↓
SQL validation
        ↓
Database execution
        ↓
Execution error
        ↓
Error sent back to LLM
        ↓
Corrected SQL attempt
```

Retries are bounded using configurable limits to prevent infinite loops.

---

# Technology Stack

## Backend

- Python
- FastAPI
- LangGraph
- PostgreSQL
- psycopg2

## AI / LLM

- OpenAI-compatible LLM endpoints
- Local LLM support through Ollama
- Schema-aware prompting

## Data Visualization

- Matplotlib
- Automatic chart selection based on query output

---

# Setup

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 2. Configure Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_llm_key

# Optional OpenAI-compatible endpoint
# OPENAI_BASE_URL=http://localhost:11434/v1

SQL_MODEL=qwen2.5:7b
INSIGHT_MODEL=qwen2.5:7b


# PostgreSQL (Neon or local PostgreSQL)

PG_HOST=your_postgres_host
PG_PORT=5432
PG_DB=your_database_name
PG_USER=your_username
PG_PASSWORD=your_password


MAX_SQL_RETRIES=2
MAX_ROWS_RETURNED=500
QUERY_TIMEOUT_MS=5000


APP_API_KEY=
```

---

# Database Setup

The project includes a synthetic e-commerce dataset containing:

- Customers
- Products
- Orders
- Order Items

To create the database tables and populate sample data:

```bash
python seed_db.py
```

Successful execution will create:

```
customers
products
orders
order_items
```

with realistic sample transaction data.

---

# Running the Application

Start the FastAPI server:

```bash
python -m uvicorn main:app --reload --port 8000
```

The application will start at:

```
http://localhost:8000
```

---

# API Endpoints

## Health Check

```
GET /health
```

Checks API and database connectivity.

---

## Database Schema

```
GET /schema
```

Returns the currently detected database schema.

---

## Chat Endpoint

```
POST /chat
```

Example request:

```json
{
  "question": "What are the top 5 products by revenue?"
}
```

Example response:

```json
{
  "type": "result",
  "sql": "SELECT ...",
  "rows": [],
  "insight": "The top revenue generating products are...",
  "chart": "..."
}
```

---

# Project Structure

```
proj-healthcare/

├── main.py
│   FastAPI application and API routes

├── graph.py
│   LangGraph agent workflow

├── db.py
│   PostgreSQL connection pooling and schema introspection

├── config.py
│   Environment configuration

├── sql_guard.py
│   SQL validation and safety checks

├── chart.py
│   Automatic visualization generation

├── seed_db.py
│   Synthetic e-commerce database generator

├── static/
│   └── index.html
│       Web interface

├── requirements.txt
│
└── .env
    Environment variables
```

---

# Future Improvements

Possible extensions:

- Support additional database engines
- Add user authentication
- Add conversational memory
- Support uploaded CSV/Excel datasets
- Add more visualization types
- Deploy as a cloud-hosted analytics assistant

---

# License

This project is intended for educational and portfolio demonstration purposes.
