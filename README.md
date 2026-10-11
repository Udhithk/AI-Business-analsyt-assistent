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

## Setup & Run

### 1. Install Dependencies
```bash
cd ai_ba_assistant
pip install -r requirements.txt
```

### 2. Configure API Key
Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) and either:
- Set it as an environment variable:
  - **Windows (PowerShell)**: `$env:GEMINI_API_KEY="AIzaSy..."`
  - **Linux / macOS**: `export GEMINI_API_KEY=AIzaSy...`
- Or enter it directly in the sidebar input field when the app is running.

### 3. Start the Application
```bash
streamlit run app.py
```

Then open `http://localhost:8501`, upload your CSV or Excel file, and ask business questions like:
- *"Why did revenue drop in March?"*
- *"Which category had the highest sales?"*
- *"Show me monthly revenue trend"*

## Architecture & Design Decisions

- **DuckDB for In-Memory Analytics**: Reads CSV/Excel directly with automatic type inference — no manual database setup per dataset.
- **Strict SQL Safety Layer**: LLM-generated SQL is strictly sandboxed. The validator enforces single `SELECT` statements only, blocks DDL/DML (`DROP`, `DELETE`, `UPDATE`, `ALTER`, etc.), prevents statement chaining, and enforces row limits.
- **Deterministic Analytics Pre-Computation**: Arithmetic (totals, averages, min/max, category breakdowns) is calculated deterministically in Python before being passed to Gemini. The LLM only narrates verified numbers, eliminating arithmetic hallucinations.

## Extensions & Roadmap
- Connect to live data warehouses (PostgreSQL, BigQuery, Snowflake).
- Extended multi-turn context memory for chained conversational drill-downs.
- Automated export of insights and interactive visualizations to PDF/PowerPoint.
