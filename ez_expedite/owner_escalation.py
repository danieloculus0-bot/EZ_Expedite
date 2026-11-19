"""Read-only owner escalation summary from the existing occurrence database.

python -m ez_expedite.owner_escalation path/to/expedite.db --as-of 2026-11-19
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .overdue_report import overdue_rows, safe_csv_rows

COLUMNS = ("owner_name", "owner_email", "overdue_cases", "oldest_days_overdue",
           "case_numbers", "unassigned")


def owner_escalations(db_path: str | Path, as_of: date) -> list[dict]:
    """Aggregate open overdue cases by assigned owner without changing the store."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in overdue_rows(db_path, as_of):
        name = str(item["owner_name"]).strip()
        email = str(item["owner_email"]).strip()
        grouped[(name, email)].append(item)
    results = []
    for (name, email), cases in grouped.items():
        cases.sort(key=lambda item: (-item["days_overdue"], item["case_number"]))
        results.append({
            "owner_name": name,
            "owner_email": email,
            "overdue_cases": len(cases),
            "oldest_days_overdue": max(c["days_overdue"] for c in cases),
            "case_numbers": "; ".join(str(c["case_number"]) for c in cases),
            "unassigned": "YES" if not name and not email else "NO",
        })
    return sorted(results, key=lambda item: (-item["oldest_days_overdue"],
                                             -item["overdue_cases"],
                                             item["owner_name"], item["owner_email"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export overdue occurrence escalation by owner")
    parser.add_argument("database", help="Existing EZ Expedite SQLite database")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", help="CSV output path, otherwise stdout")
    args = parser.parse_args(argv)
    try:
        rows = safe_csv_rows(owner_escalations(args.database, date.fromisoformat(args.as_of)))
        if args.output:
            with open(args.output, "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        parser.exit(2, f"Owner escalation report failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
