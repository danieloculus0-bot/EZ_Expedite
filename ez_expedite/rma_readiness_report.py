"""Read-only RMA stage readiness queue. Never advances or closes records."""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .rma_workflow import stage_blockers, stage_info

COLUMNS = ("case_number", "rma_number", "stage", "department", "owner_name",
           "ready", "blocker_count", "blockers")


def readiness_rows(db_path: str | Path) -> list[dict]:
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database does not exist: {path}")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        records = con.execute("""SELECT o.*,r.* FROM occurrences o
            JOIN rma_details r ON r.occurrence_id=o.id
            WHERE UPPER(TRIM(COALESCE(o.status,''))) NOT IN
            ('CLOSED','COMPLETE','COMPLETED','CANCELLED','CANCELED')
            ORDER BY o.case_number,o.id""").fetchall()
    result = []
    for row in records:
        stage = row["rma_stage"] or "INTAKE"
        blockers = (["Stage complete; close occurrence through the authorized workflow."]
                    if stage == "COMPLETE" else stage_blockers(row))
        result.append({
            "case_number": row["case_number"] or "",
            "rma_number": row["rma_number"] or "",
            "stage": stage,
            "department": stage_info(stage).role_label,
            "owner_name": row["owner_name"] or "",
            "ready": "YES" if not blockers else "NO",
            "blocker_count": len(blockers),
            "blockers": " | ".join(blockers),
        })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export read-only RMA readiness as CSV")
    parser.add_argument("database", help="Existing SQLite database")
    parser.add_argument("--output", help="Optional CSV output path")
    args = parser.parse_args(argv)
    try:
        rows = readiness_rows(args.database)
        # Escape formula-like values in every exported string field, not just
        # fields shared with the overdue-report CSV schema.
        rows = [{k: ("'" + v if isinstance(v, str) and
                  v.lstrip().startswith(("=", "+", "-", "@")) else v)
                 for k, v in row.items()} for row in rows]
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
        parser.exit(2, f"RMA readiness report failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
