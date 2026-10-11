"""
query_executor.py
Executes validated SQL against the DuckDB connection and returns
a pandas DataFrame. Kept as its own module so execution logic
(timeouts, error handling) is isolated from generation logic.
"""

import duckdb
import pandas as pd


class QueryExecutionError(Exception):
    pass


def run_query(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    """
    Executes the SQL and returns results as a DataFrame.
    Wraps errors so the app can show a friendly message instead of a raw traceback.
    """
    try:
        result_df = con.execute(sql).fetchdf()
    except Exception as e:
        raise QueryExecutionError(f"Query failed to execute: {e}")

    if result_df.empty:
        raise QueryExecutionError("Query ran successfully but returned no rows.")

    return result_df
