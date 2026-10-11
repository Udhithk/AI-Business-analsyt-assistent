"""
visualizer.py
Auto-generates a Plotly chart based purely on the SHAPE of the query
result (not the original dataset), so it works for any uploaded file:
- one date/time col + one numeric col      -> line chart
- one categorical col + one numeric col    -> bar chart
- two numeric cols                         -> scatter plot
- single numeric col                       -> histogram
- fallback                                 -> table
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _find_col_by_type(df: pd.DataFrame, kind: str):
    if kind == "datetime":
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return col
            # try parsing string columns that look like dates
            if df[col].dtype == object:
                try:
                    pd.to_datetime(df[col], errors="raise")
                    return col
                except (ValueError, TypeError):
                    continue
        return None
    elif kind == "numeric":
        cols = df.select_dtypes(include="number").columns.tolist()
        return cols[0] if cols else None
    elif kind == "categorical":
        cols = df.select_dtypes(include="object").columns.tolist()
        return cols[0] if cols else None
    return None


def auto_chart(df: pd.DataFrame, title: str = "Result"):
    """
    Returns a Plotly figure chosen automatically based on df's column types.
    """
    date_col = _find_col_by_type(df, "datetime")
    numeric_col = _find_col_by_type(df, "numeric")
    cat_col = _find_col_by_type(df, "categorical")

    if date_col and numeric_col:
        df_sorted = df.copy()
        df_sorted[date_col] = pd.to_datetime(df_sorted[date_col], errors="coerce")
        df_sorted = df_sorted.sort_values(date_col)
        fig = px.line(df_sorted, x=date_col, y=numeric_col, title=title, markers=True)

    elif cat_col and numeric_col:
        df_sorted = df.sort_values(numeric_col, ascending=False).head(20)
        fig = px.bar(df_sorted, x=cat_col, y=numeric_col, title=title)

    else:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if len(numeric_cols) >= 2:
            fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1], title=title)
        elif len(numeric_cols) == 1:
            fig = px.histogram(df, x=numeric_cols[0], title=title)
        else:
            # Fallback: render as a plain table figure
            fig = go.Figure(data=[go.Table(
                header=dict(values=list(df.columns)),
                cells=dict(values=[df[c] for c in df.columns])
            )])
            fig.update_layout(title=title)

    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    return fig
