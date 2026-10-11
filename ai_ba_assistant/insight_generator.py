"""
insight_generator.py
Turns query results into a business-language narrative.

Key design choice: numeric deltas/comparisons are computed in plain
Python (deterministic, verifiable) and only the NARRATION is left to
the LLM. This avoids the failure mode of the LLM doing arithmetic
wrong and confidently reporting incorrect numbers.
"""

import pandas as pd
from google import genai

MODEL = "gemini-3.6-flash"

INSIGHT_SYSTEM_PROMPT = """You are a business analyst explaining query results to a non-technical
stakeholder. You will be given the original question, the data returned, and (when relevant)
pre-computed statistics/deltas.

Rules:
- Write 3-5 sentences, business-plain-English, no jargon, no SQL talk.
- Never invent numbers that are not present in the data or stats provided to you.
- If the data suggests a change (increase/decrease), state it and give the most plausible drivers
  visible in the data (e.g. which category or segment moved most).
- If the data doesn't clearly support a causal explanation, say what the data shows without
  overclaiming why.
- Format like the example: a one-line headline finding, then 2-4 bullet-style supporting points.
"""


def _compute_basic_stats(df: pd.DataFrame) -> str:
    """
    Computes deterministic summary stats in Python so the LLM
    doesn't have to (and can't get wrong) the actual math.
    """
    stats_lines = []
    numeric_cols = df.select_dtypes(include="number").columns

    for col in numeric_cols:
        total = df[col].sum()
        mean = df[col].mean()
        stats_lines.append(f"- {col}: total={total:.2f}, average={mean:.2f}, "
                            f"min={df[col].min():.2f}, max={df[col].max():.2f}")

    # If there's an obvious categorical + numeric pair, show top/bottom movers
    cat_cols = df.select_dtypes(include="object").columns
    if len(cat_cols) > 0 and len(numeric_cols) > 0:
        cat_col = cat_cols[0]
        num_col = numeric_cols[0]
        grouped = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False)
        if len(grouped) > 1:
            stats_lines.append(f"\nBreakdown of {num_col} by {cat_col} (highest to lowest):")
            stats_lines.append(grouped.to_string())

    return "\n".join(stats_lines) if stats_lines else "No numeric columns to summarize."


def generate_insight(question: str, df: pd.DataFrame, client: genai.Client, prior_question: str = None) -> str:
    """
    Produces the final business-language insight paragraph.
    """
    computed_stats = _compute_basic_stats(df)
    data_preview = df.head(20).to_string(index=False)

    prior_context = ""
    if prior_question:
        prior_context = f"Previous question context: User previously asked: \"{prior_question}\"\n"

    user_prompt = f"""{prior_context}Original question: "{question}"

Query result data (preview, up to 20 rows):
{data_preview}

Pre-computed statistics (trust these numbers exactly, do not recalculate):
{computed_stats}

Write the business insight now."""

    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config={
            "system_instruction": INSIGHT_SYSTEM_PROMPT,
            "max_output_tokens": 600,
        },
    )

    return response.text.strip()
