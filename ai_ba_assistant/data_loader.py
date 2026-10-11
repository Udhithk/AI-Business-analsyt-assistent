"""
data_loader.py
Loads any uploaded CSV/Excel file into DuckDB and auto-generates
a schema profile (columns, types, samples, stats) that gets fed
to the LLM so it can write correct SQL against ANY dataset.
"""

import duckdb
import pandas as pd
import os
import re


def load_file_to_duckdb(file_path: str, table_name: str = "data") -> duckdb.DuckDBPyConnection:
    """
    Loads a CSV or Excel file into an in-memory DuckDB table.
    Returns a live DuckDB connection with the table ready to query.
    """
    con = duckdb.connect(database=":memory:")
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        # DuckDB's read_csv_auto infers types + delimiters automatically
        con.execute(f"""
            CREATE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{file_path}', SAMPLE_SIZE=-1)
        """)
    elif ext in (".xlsx", ".xls"):
        # DuckDB doesn't read Excel natively -> load via pandas, then register
        df = pd.read_excel(file_path)
        df = _clean_column_names(df)
        con.register("temp_df", df)
        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_df")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use .csv or .xlsx")

    return con


def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Strips whitespace from column names so SQL references don't break."""
    df.columns = [str(c).strip() for c in df.columns]
    return df


def sanitize_table_name(filename: str, existing_names: set) -> str:
    """Sanitizes filename into a clean, unique SQL table name."""
    base = os.path.splitext(os.path.basename(filename))[0]
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", base).lower()
    if not sanitized or sanitized[0].isdigit():
        sanitized = "_" + sanitized
    
    candidate = sanitized
    counter = 1
    while candidate in existing_names:
        candidate = f"{sanitized}_{counter}"
        counter += 1
    return candidate


def load_multiple_files_to_duckdb(files_and_paths: list) -> duckdb.DuckDBPyConnection:
    """
    Loads multiple CSV or Excel files into a single in-memory DuckDB connection.
    files_and_paths is a list of tuples: (temp_file_path, original_filename)
    """
    con = duckdb.connect(database=":memory:")
    existing_names = set()
    for path, filename in files_and_paths:
        table_name = sanitize_table_name(filename, existing_names)
        existing_names.add(table_name)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            con.execute(f"""
                CREATE TABLE "{table_name}" AS
                SELECT * FROM read_csv_auto('{path}', SAMPLE_SIZE=-1)
            """)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(path)
            df = _clean_column_names(df)
            con.register("temp_df", df)
            con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM temp_df')
            con.unregister("temp_df")
        else:
            raise ValueError(f"Unsupported file type: {ext}. Use .csv or .xlsx")
    return con


def get_table_names(con: duckdb.DuckDBPyConnection) -> list:
    """Retrieves all table names inside the DuckDB connection."""
    res = con.execute("SHOW TABLES").fetchall()
    return [r[0] for r in res]


def profile_schema(con: duckdb.DuckDBPyConnection, table_name: str = "data") -> str:
    """
    Generates a plain-text schema profile for the given table:
    - column names + types
    - sample rows
    - basic stats for numeric columns
    - top values for categorical columns
    This text gets injected directly into the SQL-generation prompt.
    """
    columns_info = con.execute(f'DESCRIBE "{table_name}"').fetchdf()
    sample_rows = con.execute(f'SELECT * FROM "{table_name}" LIMIT 5').fetchdf()
    row_count = con.execute(f'SELECT COUNT(*) AS n FROM "{table_name}"').fetchone()[0]

    lines = [f"Table: {table_name}", f"Row count: {row_count}", "", "Columns:"]

    for _, row in columns_info.iterrows():
        col_name = row["column_name"]
        col_type = row["column_type"]
        line = f"  - \"{col_name}\" ({col_type})"

        # Add extra context depending on type
        if any(t in col_type for t in ["INT", "DOUBLE", "DECIMAL", "FLOAT", "BIGINT"]):
            stats = con.execute(f"""
                SELECT MIN("{col_name}") AS min_v, MAX("{col_name}") AS max_v,
                       AVG("{col_name}") AS avg_v
                FROM "{table_name}"
            """).fetchone()
            line += f" | min={stats[0]}, max={stats[1]}, avg={round(stats[2], 2) if stats[2] is not None else None}"

        elif any(t in col_type for t in ["VARCHAR", "TEXT"]):
            uniq = con.execute(f'SELECT COUNT(DISTINCT "{col_name}") FROM "{table_name}"').fetchone()[0]
            if uniq <= 20:
                top_vals = con.execute(f"""
                    SELECT DISTINCT "{col_name}" FROM "{table_name}"
                    WHERE "{col_name}" IS NOT NULL LIMIT 10
                """).fetchdf()[col_name].tolist()
                line += f" | {uniq} unique values, e.g. {top_vals}"
            else:
                line += f" | {uniq} unique values (high cardinality, likely an ID or free text)"

        lines.append(line)

    lines.append("")
    lines.append("Sample rows:")
    lines.append(sample_rows.to_string(index=False))

    return "\n".join(lines)


def profile_combined_schema(con: duckdb.DuckDBPyConnection) -> str:
    """Generates a combined schema profile across all loaded tables, with join hints."""
    table_names = get_table_names(con)
    profiles = []
    profiles.append("=== MULTI-TABLE DATABASE SCHEMA ===")
    profiles.append("Note: If a question needs data from more than one table, they should be answered by JOINing the tables on matching column names (e.g., a shared customer_id).")
    profiles.append("")

    for t in table_names:
        profiles.append(profile_schema(con, t))
        profiles.append("-" * 40)

    return "\n".join(profiles)
