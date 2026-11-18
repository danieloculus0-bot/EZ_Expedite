"""Read-only action queue for occurrences due within an inclusive date window.

Usage: python -m ez_expedite.due_soon_report path/to/db --as-of 2026-11-18 --days 7
No database writes, external notifications or credentials.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from .overdue_report import COLUMNS, safe_csv_rows


def due_soon_rows(db_path: str | Path, as_of: date, days: int = 7) -> list[dict]:
    if days < 0 or days > 366:
        raise ValueError("days must be between 0 and 366")
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        records = con.execute(
            """SELECT case_number,title,status,owner_name,owner_email,due_date,next_action
               FROM occurrences
               WHERE due_date IS NOT NULL AND TRIM(due_date) != ''
                 AND UPPER(TRIM(COALESCE(status,''))) NOT IN
                     ('CLOSED','COMPLETE','COMPLETED','CANCELLED','CANCELED')
               ORDER BY due_date,case_number"""
        ).fetchall()
    end = as_of + timedelta(days=days)
    result = []
    for record in records:
        raw = record["due_date"].strip()
        try:
            due = date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"Invalid due_date for {record['case_number']}: {raw!r}") from None
        if not as_of <= due <= end:
            continue
        item = {key: record[key] or "" for key in COLUMNS if key != "days_overdue"}
        item["days_overdue"] = 0
        item["days_until_due"] = (due - as_of).days
        result.append(item)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export upcoming open occurrences as CSV")
    parser.add_argument("database", help="Existing EZ Expedite SQLite database")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="ISO date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7, help="Inclusive forward window, 0 to 366 days")
    parser.add_argument("--output", help="CSV path; defaults to stdout")
    args = parser.parse_args(argv)
    fields = (*COLUMNS, "days_until_due")
    try:
        rows = safe_csv_rows(due_soon_rows(args.database, date.fromisoformat(args.as_of), args.days))
        if args.output:
            with open(args.output, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, OverflowError, sqlite3.DatabaseError) as exc:
        parser.exit(2, f"Upcoming due report failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
