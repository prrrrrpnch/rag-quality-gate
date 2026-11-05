"""SQL data validation: the same queries on Athena (S3) and DuckDB (local)."""

from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[3] / "sql"
ZERO_ROW_CHECKS = ("pii_leak_check", "data_quality_check")
REPORT_QUERIES = ("quality_trend", "latency_cost")


def render_sql(name: str, **params: str) -> str:
    """Load ``sql/<name>.sql`` and substitute ``{{param}}`` placeholders."""
    text = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    params.setdefault("since", "2026-01-01")
    for k, v in params.items():
        text = text.replace("{{" + k + "}}", v)
    return text
