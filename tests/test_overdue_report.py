from __future__ import annotations

import csv
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import date
from pathlib import Path

from ez_expedite.db import init_db
from ez_expedite.overdue_report import main, overdue_rows


class OverdueReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "occurrences.db"
        init_db(self.db)
        with closing(sqlite3.connect(self.db)) as con, con:
            type_id = con.execute("SELECT id FROM occurrence_types WHERE name='RMA'").fetchone()[0]
            for number, due, status in (
                ("SYN-001", "2026-11-10", "NEW"),
                ("SYN-002", "2026-11-17", "NEW"),
                ("SYN-003", "2026-11-01", "CLOSED"),
                ("SYN-004", None, "INVESTIGATING"),
            ):
                con.execute(
                    """INSERT INTO occurrences(case_number,occurrence_type_id,title,status,
                       due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
                    (number, type_id, "Synthetic occurrence", status, due,
                     "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"),
                )

    def test_overdue_only_and_elapsed_days(self):
        rows = overdue_rows(self.db, date(2026, 11, 17))
        self.assertEqual([row["case_number"] for row in rows], ["SYN-001"])
        self.assertEqual(rows[0]["days_overdue"], 7)

    def test_csv_end_to_end(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.db), "--as-of", "2026-11-17"]), 0)
        records = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["days_overdue"], "7")

    def test_csv_formula_injection_is_neutralized_without_mutating_source(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute(
                "UPDATE occurrences SET title=?, owner_name=?, next_action=? WHERE case_number='SYN-001'",
                ("=HYPERLINK(\\\"https://invalid.example\\\")", "  +SUM(1,2)", "@cmd")
            )
        raw = overdue_rows(self.db, date(2026, 11, 17))[0]
        self.assertTrue(raw["title"].startswith("="))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.db), "--as-of", "2026-11-17"]), 0)
        exported = next(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(exported["title"], "'" + raw["title"])
        self.assertEqual(exported["owner_name"], "'" + raw["owner_name"])
        self.assertEqual(exported["next_action"], "'@cmd")
        self.assertEqual(exported["days_overdue"], "7")
        self.assertEqual(overdue_rows(self.db, date(2026, 11, 17))[0]["title"], raw["title"])

    def test_missing_database_does_not_create_file(self):
        missing = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            overdue_rows(missing, date(2026, 11, 17))
        self.assertFalse(missing.exists())

    def test_invalid_date_rejected(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE occurrences SET due_date='bad-date' WHERE case_number='SYN-001'")
        with self.assertRaisesRegex(ValueError, "SYN-001"):
            overdue_rows(self.db, date(2026, 11, 17))

    def test_read_only_database(self):
        before = self.db.read_bytes()
        overdue_rows(self.db, date(2026, 11, 17))
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
