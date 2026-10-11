"""
app.py
Streamlit UI for the AI Business Analyst Assistant.

Flow:
  1. User uploads a CSV/Excel file (any dataset)
  2. File is loaded into DuckDB, schema is auto-profiled
  3. User asks a question in plain English
  4. Question + schema -> SQL (Claude)
  5. SQL -> DuckDB -> DataFrame
  6. DataFrame -> business insight (Claude, deterministic stats underneath)
  7. DataFrame -> auto chart (Plotly)

Run with: streamlit run app.py
"""

import os
import tempfile

import streamlit as st
from google import genai

from data_loader import load_multiple_files_to_duckdb, profile_combined_schema
from sql_generator import generate_sql, UnsafeSQLError
from query_executor import run_query, QueryExecutionError
from insight_generator import generate_insight
from visualizer import auto_chart

st.set_page_config(page_title="AI Business Analyst Assistant", layout="wide")
st.title("AI Business Analyst Assistant")
st.caption("Upload any dataset. Ask a business question in plain English. Get SQL, data, chart, and insight.")

# --- API key handling ---
api_key = os.environ.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("Setup")
    if not api_key:
        api_key = st.text_input("Gemini API key", type="password",
                                 help="Or set the GEMINI_API_KEY environment variable.")
    st.divider()
    if "history" in st.session_state and st.session_state.history:
        if st.button("Clear conversation"):
            st.session_state.history = []
            st.rerun()
        st.divider()
    st.markdown("**How it works**\n\n"
                "1. Upload one or more CSV or Excel files\n"
                "2. Schemas are auto-detected\n"
                "3. Ask questions about the data\n"
                "4. The assistant writes SQL, runs it, and explains the result")

if not api_key:
    st.warning("Enter your Gemini API key in the sidebar to continue.")
    st.stop()

client = genai.Client(api_key=api_key)

# --- File upload ---
uploaded_files = st.file_uploader("Upload dataset(s)", type=["csv", "xlsx", "xls"], accept_multiple_files=True)

if "history" not in st.session_state:
    st.session_state.history = []

if uploaded_files is not None and len(uploaded_files) > 0:
    current_files = [f.name for f in uploaded_files]

    # Reset history and load/profile if the uploaded files list changed
    if "loaded_files" not in st.session_state or st.session_state.loaded_files != current_files:
        st.session_state.history = []
        with st.spinner("Loading datasets and profiling schemas..."):
            files_and_paths = []
            for uploaded_file in uploaded_files:
                suffix = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.getbuffer())
                    tmp_path = tmp.name
                files_and_paths.append((tmp_path, uploaded_file.name))

            con = load_multiple_files_to_duckdb(files_and_paths)
            schema_text = profile_combined_schema(con)

        st.session_state.con = con
        st.session_state.schema_text = schema_text
        st.session_state.loaded_files = current_files

    con = st.session_state.con
    schema_text = st.session_state.schema_text

    with st.expander("Detected schema"):
        st.code(schema_text)

    # --- Conversation History Expander ---
    if st.session_state.history:
        with st.expander("Conversation History", expanded=False):
            for i, turn in enumerate(st.session_state.history):
                st.markdown(f"**Turn {i+1}:** {turn['question']}")
                st.code(turn['sql'], language="sql")

    # --- Question input ---
    question = st.text_input("Ask a business question about this data",
                              placeholder="e.g. Why did revenue drop in March?")

    if st.button("Analyze", type="primary") and question:
        try:
            with st.spinner("Writing SQL..."):
                sql = generate_sql(question, schema_text, client, st.session_state.history)

            with st.expander("Generated SQL"):
                st.code(sql, language="sql")

            with st.spinner("Running query..."):
                result_df = run_query(con, sql)

            st.subheader("Data")
            st.dataframe(result_df, use_container_width=True)

            st.subheader("Chart")
            fig = auto_chart(result_df, title=question)
            st.plotly_chart(fig, use_container_width=True)

            prior_question = st.session_state.history[-1]["question"] if st.session_state.history else None
            with st.spinner("Generating insight..."):
                insight = generate_insight(question, result_df, client, prior_question)

            st.subheader("Insight")
            st.markdown(insight)

            # Save completed turn to history on successful run
            st.session_state.history.append({
                "question": question,
                "sql": sql
            })

        except UnsafeSQLError as e:
            st.error(f"Couldn't generate a safe query: {e}")
        except QueryExecutionError as e:
            st.error(f"Query error: {e}")
        except Exception as e:
            st.error(f"Something went wrong: {e}")
else:
    st.info("Upload one or more CSV or Excel files to get started.")
