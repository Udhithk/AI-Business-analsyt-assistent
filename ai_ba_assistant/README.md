# AI Business Analyst Assistant

Upload any dataset (CSV or Excel), ask a business question in plain English,
and get: generated SQL, the raw data, an auto-picked chart, and a written
insight explaining what happened and why.

## How it works

1. **Upload** — any CSV/Excel file is loaded into an in-memory DuckDB table.
2. **Schema profiling** (`data_loader.py`) — column names, types, sample rows,
   and basic stats are auto-extracted so the assistant works on ANY schema,
   not a fixed one.
3. **SQL generation** (`sql_generator.py`) — Gemini converts your question into
   a SQL query using the profiled schema as context. Every query is validated:
   only `SELECT` statements are allowed, no DDL/DML, no statement chaining,
   and a hard row limit is enforced.
4. **Execution** (`query_executor.py`) — the validated SQL runs against DuckDB
   (read-only) and returns a pandas DataFrame.
5. **Insight generation** (`insight_generator.py`) — numeric deltas and
   breakdowns are computed in plain Python first (deterministic, so the
   numbers are always correct), and Gemini only narrates those pre-computed
   stats in business language.
6. **Visualization** (`visualizer.py`) — a chart type is auto-picked based on
   the shape of the result (time series -> line, category -> bar, etc).

## Setup

```bash
pip install -r requirements.txt
```

Get a Gemini API key from https://aistudio.google.com/apikey (note that `gemini-3.6-flash` is free-tier eligible) and either:
- set it as an environment variable: `export GEMINI_API_KEY=AIzaSy...`
- or paste it into the sidebar when the app runs

## Run

```bash
streamlit run app.py
```

Then open the local URL Streamlit prints, upload a CSV/Excel file, and ask
a question like:

> Why did revenue drop in March?
> Which category had the highest sales?
> Show me monthly revenue trend

## Design notes worth knowing for an interview

- **Why DuckDB instead of SQLite/Postgres**: it reads CSV/Excel directly with
  automatic type inference — no manual schema setup per dataset, which is
  what makes this work on *any* upload.
- **Why SQL safety validation exists**: LLM-generated SQL should never be
  trusted with write access. The validator blocks anything but a single
  `SELECT`, rejects DDL/DML keywords, blocks statement chaining, and caps
  row counts.
- **Why insight math is computed in Python, not by the LLM**: LLMs are
  unreliable at arithmetic on large tables. Computing sums/averages/deltas
  deterministically and only asking the LLM to *narrate* them means the
  numbers in the final insight are always correct.

## Possible extensions

- Swap DuckDB for a real Postgres/MySQL connection for live company data.
- Add conversation memory so follow-up questions ("now break that down by
  region") reuse context.
- Add authentication + per-user file storage for a multi-user demo.
- Export the insight + chart to a PDF/PowerPoint report.
