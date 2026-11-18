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
from ez_expedite.due_soon_report import due_soon_rows, main


class DueSoonReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "synthetic.db"
        init_db(self.db)
        with closing(sqlite3.connect(self.db)) as con, con:
            kind = con.execute("SELECT id FROM occurrence_types WHERE name='RMA'").fetchone()[0]
            for number, due, status in (
                ("SYN-PAST", "2026-11-17", "NEW"),
                ("SYN-TODAY", "2026-11-18", "NEW"),
                ("SYN-END", "2026-11-25", "INVESTIGATING"),
                ("SYN-LATER", "2026-11-26", "NEW"),
                ("SYN-CLOSED", "2026-11-19", "CLOSED"),
                ("SYN-EMPTY", None, "NEW"),
            ):
                con.execute(
                    """INSERT INTO occurrences(case_number,occurrence_type_id,title,status,
                       due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
                    (number, kind, "Synthetic action", status, due,
                     "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"),
                )

    def test_inclusive_window_excludes_past_closed_and_future(self):
        rows = due_soon_rows(self.db, date(2026, 11, 18), 7)
        self.assertEqual([r["case_number"] for r in rows], ["SYN-TODAY", "SYN-END"])
        self.assertEqual([r["days_until_due"] for r in rows], [0, 7])

    def test_zero_day_window(self):
        self.assertEqual([r["case_number"] for r in due_soon_rows(self.db, date(2026, 11, 18), 0)], ["SYN-TODAY"])

    def test_csv_cli_and_injection_guard(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE occurrences SET title='=2+2' WHERE case_number='SYN-TODAY'")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.db), "--as-of", "2026-11-18", "--days", "7"]), 0)
        rows = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "'=2+2")
        self.assertEqual(rows[1]["days_until_due"], "7")
        self.assertEqual(due_soon_rows(self.db, date(2026, 11, 18))[0]["title"], "=2+2")

    def test_read_only(self):
        before = self.db.read_bytes()
        due_soon_rows(self.db, date(2026, 11, 18))
        self.assertEqual(self.db.read_bytes(), before)

    def test_invalid_window_and_missing_database(self):
        for days in (-1, 367):
            with self.assertRaises(ValueError):
                due_soon_rows(self.db, date(2026, 11, 18), days)
        missing = Path(self.temp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            due_soon_rows(missing, date(2026, 11, 18))
        self.assertFalse(missing.exists())

    def test_invalid_source_date_is_not_silently_ignored(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE occurrences SET due_date='bad' WHERE case_number='SYN-TODAY'")
        with self.assertRaisesRegex(ValueError, "SYN-TODAY"):
            due_soon_rows(self.db, date(2026, 11, 18))


if __name__ == "__main__":
    unittest.main()
