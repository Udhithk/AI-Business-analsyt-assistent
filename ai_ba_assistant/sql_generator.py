"""
sql_generator.py
Converts a natural-language business question into SQL, using the
auto-generated schema profile as context. Includes strict safety
checks so nothing but a read-only SELECT can ever be executed.
"""

import re
from google import genai

MODEL = "gemini-3.6-flash"

SQL_SYSTEM_PROMPT = """You are a SQL generation engine for a business analytics tool.
You will be given a table schema (which may contain multiple tables) and a business question in plain English.

Rules:
- Output ONLY a single valid DuckDB SQL SELECT statement. No explanation, no markdown, no backticks.
- Only ever generate SELECT statements. Never INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or any DDL/DML.
- Always quote column names with double quotes, exactly as given in the schema (case-sensitive, may contain spaces).
- If multiple tables are present in the schema, you can JOIN them using matching column/ID names when needed.
- Always qualify column names with their respective table names when multiple tables are present (e.g., "table_name"."column_name") to avoid ambiguity.
- If the question implies a time comparison ("drop in March", "vs last quarter"), write SQL that returns
  the raw rows/aggregates needed for that comparison — do not try to compute the final narrative yourself.
- If the question is ambiguous or unanswerable from the schema, return exactly: NO_QUERY_POSSIBLE
- Never invent column names that are not in the schema.
"""


class UnsafeSQLError(Exception):
    pass


def _is_safe_select(sql: str) -> bool:
    """
    Defense-in-depth check: only allow a single SELECT statement.
    Blocks any write/DDL keywords even if the LLM tries to sneak them in.
    """
    stripped = sql.strip().rstrip(";")

    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        return False

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                 "TRUNCATE", "ATTACH", "COPY", "PRAGMA", "EXPORT", "IMPORT"]
    upper_sql = stripped.upper()
    if any(f" {kw} " in f" {upper_sql} " or upper_sql.startswith(kw) for kw in forbidden):
        return False

    # Block statement chaining (e.g. "SELECT ...; DROP TABLE ...")
    if ";" in stripped:
        return False

    # Block incomplete / truncated SQL with unbalanced quotes or parentheses
    if stripped.count('"') % 2 != 0:
        return False
    if stripped.count("'") % 2 != 0:
        return False
    if stripped.count("(") != stripped.count(")"):
        return False

    return True


def generate_sql(question: str, schema_text: str, client: genai.Client, history: list = None) -> str:
    """
    Calls Gemini to convert the question into SQL, validates it,
    and returns a safe SQL string ready for execution.
    Raises UnsafeSQLError if the model returns anything unsafe.
    """
    history_text = ""
    if history:
        history_text = "\nPrior Conversation History (last 3 turns):\n"
        for turn in history[-3:]:
            history_text += f"User question: {turn['question']}\nGenerated SQL: {turn['sql']}\n\n"

    user_prompt = f"""Schema:
{schema_text}
{history_text}
Business question: "{question}"

Return only the SQL query."""

    config = {
        "system_instruction": SQL_SYSTEM_PROMPT,
        "max_output_tokens": 2048,
        "thinking_config": {"thinking_budget": 0},
    }

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=config,
        )
    except Exception:
        # Fallback if model/SDK doesn't support thinking_config
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config={
                "system_instruction": SQL_SYSTEM_PROMPT,
                "max_output_tokens": 2048,
            },
        )

    sql = response.text.strip()
    if "```" in sql:
        matches = re.findall(r"```(?:sql)?\s*([\s\S]*?)\s*```", sql, re.IGNORECASE)
        if matches:
            sql = matches[0].strip()
        else:
            sql = sql.replace("```sql", "").replace("```", "").strip()

    if sql == "NO_QUERY_POSSIBLE":
        raise UnsafeSQLError("The question can't be answered from this dataset's schema.")

    if not _is_safe_select(sql):
        raise UnsafeSQLError(f"Generated SQL failed the safety/validation check and was blocked: {sql}")

    # Add a hard row limit as a final safety net against runaway result sets
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 1000"

    return sql
