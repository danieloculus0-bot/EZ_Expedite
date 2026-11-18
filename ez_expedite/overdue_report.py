"""Read-only overdue occurrence report for the existing EZ Expedite SQLite store.

Usage: python -m ez_expedite.overdue_report path/to/expedite.db --as-of 2026-11-17
No database initialization or mutation occurs.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
import sqlite3
import sys
from datetime import date
from pathlib import Path


COLUMNS = ("case_number", "title", "status", "owner_name", "owner_email",
           "due_date", "days_overdue", "next_action")


def overdue_rows(db_path: str | Path, as_of: date) -> list[dict]:
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    # SQLite URI mode=ro prevents accidental database creation or writes.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        records = con.execute(
            """SELECT case_number,title,status,owner_name,owner_email,due_date,next_action
               FROM occurrences
               WHERE due_date IS NOT NULL AND TRIM(due_date) != ''
                 AND UPPER(COALESCE(status,'')) NOT IN ('CLOSED','COMPLETE','CANCELLED')
               ORDER BY due_date,case_number"""
        ).fetchall()
    result = []
    for record in records:
        raw = record["due_date"].strip()
        try:
            due = date.fromisoformat(raw)
        except ValueError:
            # Invalid source data must not silently become a fabricated date.
            raise ValueError(f"Invalid due_date for {record['case_number']}: {raw!r}") from None
        if due >= as_of:
            continue
        item = {key: record[key] or "" for key in COLUMNS if key != "days_overdue"}
        item["days_overdue"] = (as_of - due).days
        result.append(item)
    return result


def safe_csv_rows(rows: list[dict]) -> list[dict]:
    """Prevent spreadsheet formula execution when a report is opened in Excel."""
    safe = []
    for row in rows:
        item = dict(row)
        for key in COLUMNS:
            value = item.get(key, "")
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                item[key] = "'" + value
        safe.append(item)
    return safe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export overdue open occurrences as CSV")
    parser.add_argument("database", help="Existing EZ Expedite SQLite database")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="ISO date YYYY-MM-DD")
    parser.add_argument("--output", help="CSV path; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        as_of = date.fromisoformat(args.as_of)
        rows = safe_csv_rows(overdue_rows(args.database, as_of))
        if args.output:
            with open(args.output, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        parser.exit(2, f"Overdue report failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
