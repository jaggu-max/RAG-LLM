"""Marksheet analytics engine — programmatic computation of marks/ranks."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.core.logging import get_logger

log = get_logger(__name__)


def detect_marksheet_query(query: str) -> Optional[str]:
    """Detect marksheet-related queries and return the operation type."""
    query_lower = query.lower()

    patterns = {
        "topper": r"(who is the topper|top student|highest total|first rank|topper name)",
        "top_n": r"(top \d+|best \d+|highest \d+ students)",
        "highest_subject": r"(who scored highest|highest marks|best score|maximum.*in)\s+\w+",
        "average": r"(average|mean)\s+(marks|score)",
        "compare": r"compare\s+.+\s+(and|vs|with)\s+",
        "pass_percentage": r"(pass percentage|pass rate|how many passed)",
        "lowest": r"(lowest|minimum|least)\s+(marks|score|total)",
        "subject_analysis": r"(subject analysis|subject wise|analyze.*subject)",
        "student_info": r"(marks of|scores? of|result of)\s+\w+",
        "rank": r"(rank|position|standing)\s+of",
    }

    for op, pattern in patterns.items():
        if re.search(pattern, query_lower):
            return op

    return None


def compute_from_dataframe(df: pd.DataFrame, operation: str, query: str = "") -> str:
    """Perform programmatic computation on marksheet data."""
    if df.empty:
        return "No marksheet data available."

    # Identify numeric columns (marks)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    # Try to identify key columns
    name_col = _find_column(df, ["name", "student", "student_name"])
    usn_col = _find_column(df, ["usn", "roll", "roll_no", "enrollment"])
    total_col = _find_column(df, ["total", "grand_total", "aggregate", "marks_total"])

    # If no total column, calculate it from numeric columns
    if not total_col and numeric_cols:
        subject_cols = [c for c in numeric_cols if c not in [name_col, usn_col]]
        if subject_cols:
            df["_calculated_total"] = df[subject_cols].sum(axis=1)
            total_col = "_calculated_total"

    try:
        if operation == "topper":
            return _compute_topper(df, name_col, usn_col, total_col)
        elif operation == "top_n":
            n = int(re.search(r"\d+", query).group()) if re.search(r"\d+", query) else 5
            return _compute_top_n(df, name_col, usn_col, total_col, n)
        elif operation == "highest_subject":
            return _compute_highest_subject(df, name_col, query, numeric_cols)
        elif operation == "average":
            return _compute_average(df, numeric_cols, query)
        elif operation == "compare":
            return _compute_compare(df, name_col, query, numeric_cols, total_col)
        elif operation == "pass_percentage":
            return _compute_pass_percentage(df)
        elif operation == "lowest":
            return _compute_lowest(df, name_col, usn_col, total_col)
        elif operation == "subject_analysis":
            return _compute_subject_analysis(df, numeric_cols)
        else:
            return _compute_topper(df, name_col, usn_col, total_col)
    except Exception as e:
        log.error("Marksheet computation error: %s", e)
        return f"Error computing marksheet analysis: {e}"


def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        for col in df.columns:
            if c.lower() in col.lower():
                return col
    return None


def _compute_topper(df, name_col, usn_col, total_col) -> str:
    if not total_col:
        return "Cannot determine topper — no total/aggregate column found."
    idx = df[total_col].idxmax()
    row = df.loc[idx]
    name = row[name_col] if name_col else "Unknown"
    usn = row[usn_col] if usn_col else "N/A"
    total = row[total_col]
    return f"**Topper:** {name}\n**USN:** {usn}\n**Total Marks:** {total}"


def _compute_top_n(df, name_col, usn_col, total_col, n) -> str:
    if not total_col:
        return "Cannot determine ranking — no total column found."
    sorted_df = df.sort_values(by=total_col, ascending=False).head(n)
    lines = [f"**Top {n} Students:**\n"]
    for rank, (_, row) in enumerate(sorted_df.iterrows(), 1):
        name = row[name_col] if name_col else "Unknown"
        usn = row[usn_col] if usn_col else ""
        total = row[total_col]
        usn_part = f" (USN: {usn})" if usn else ""
        lines.append(f"{rank}. {name}{usn_part} — Total: {total}")
    return "\n".join(lines)


def _compute_highest_subject(df, name_col, query, numeric_cols) -> str:
    # Extract subject from query
    for col in numeric_cols:
        if col.lower() in query.lower():
            idx = df[col].idxmax()
            row = df.loc[idx]
            name = row[name_col] if name_col else "Unknown"
            marks = row[col]
            return f"**Highest in {col}:** {name} with {marks} marks"
    return "Could not identify the subject. Available subjects: " + ", ".join(numeric_cols)


def _compute_average(df, numeric_cols, query) -> str:
    # Check for specific subject
    for col in numeric_cols:
        if col.lower() in query.lower():
            avg = df[col].mean()
            return f"**Average {col} score:** {avg:.2f}"
    # Overall average
    lines = ["**Average Marks by Subject:**"]
    for col in numeric_cols:
        if col not in ["_calculated_total"]:
            lines.append(f"- {col}: {df[col].mean():.2f}")
    return "\n".join(lines)


def _compute_compare(df, name_col, query, numeric_cols, total_col) -> str:
    if not name_col:
        return "Cannot compare — no name column found."
    # Extract names
    names = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", query)
    if len(names) < 2:
        return "Please specify two student names to compare."
    results = []
    for name in names[:2]:
        match = df[df[name_col].str.contains(name, case=False, na=False)]
        if not match.empty:
            results.append((name, match.iloc[0]))
    if len(results) < 2:
        return f"Could not find both students. Found: {[r[0] for r in results]}"
    lines = [f"**Comparison: {results[0][0]} vs {results[1][0]}**\n"]
    for col in numeric_cols:
        if col != "_calculated_total":
            v1 = results[0][1].get(col, "N/A")
            v2 = results[1][1].get(col, "N/A")
            lines.append(f"- {col}: {v1} vs {v2}")
    if total_col:
        lines.append(f"\n**Total:** {results[0][1].get(total_col, 'N/A')} vs {results[1][1].get(total_col, 'N/A')}")
    return "\n".join(lines)


def _compute_pass_percentage(df) -> str:
    result_col = _find_column(df, ["result", "status", "pass_fail"])
    if result_col:
        passed = df[result_col].str.lower().str.contains("pass", na=False).sum()
        total = len(df)
        pct = (passed / total * 100) if total else 0
        return f"**Pass Percentage:** {pct:.1f}% ({passed}/{total} students)"
    return "Cannot determine pass percentage — no result column found."


def _compute_lowest(df, name_col, usn_col, total_col) -> str:
    if not total_col:
        return "Cannot determine — no total column found."
    idx = df[total_col].idxmin()
    row = df.loc[idx]
    name = row[name_col] if name_col else "Unknown"
    total = row[total_col]
    return f"**Lowest Total:** {name} with {total} marks"


def _compute_subject_analysis(df, numeric_cols) -> str:
    lines = ["**Subject-wise Analysis:**\n"]
    for col in numeric_cols:
        if col != "_calculated_total":
            lines.append(f"**{col}:**")
            lines.append(f"  - Average: {df[col].mean():.2f}")
            lines.append(f"  - Highest: {df[col].max()}")
            lines.append(f"  - Lowest: {df[col].min()}")
            lines.append(f"  - Std Dev: {df[col].std():.2f}")
            lines.append("")
    return "\n".join(lines)


def try_load_marksheet(filepath: str) -> Optional[pd.DataFrame]:
    """Try to load a marksheet file as a DataFrame."""
    try:
        if filepath.endswith(".csv"):
            return pd.read_csv(filepath)
        elif filepath.endswith(".xlsx") or filepath.endswith(".xls"):
            return pd.read_excel(filepath)
        return None
    except Exception as e:
        log.error("Failed to load marksheet %s: %s", filepath, e)
        return None
