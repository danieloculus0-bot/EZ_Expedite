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
from ez_expedite.owner_escalation import main, owner_escalations


class OwnerEscalationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "cases.db"
        init_db(self.db)
        with closing(sqlite3.connect(self.db)) as con, con:
            kind = con.execute("SELECT id FROM occurrence_types WHERE name='RMA'").fetchone()[0]
            cases = [
                ("SYN-1", "2026-11-10", "OPEN", "Alex", "alex@example.invalid"),
                ("SYN-2", "2026-11-15", "OPEN", "Alex", "alex@example.invalid"),
                ("SYN-3", "2026-11-01", "CLOSED", "Alex", "alex@example.invalid"),
                ("SYN-4", "2026-11-12", "OPEN", None, None),
                ("SYN-5", "2026-11-20", "OPEN", "Sam", "sam@example.invalid"),
                ("SYN-6", None, "OPEN", "Sam", "sam@example.invalid"),
            ]
            for number, due, status, owner, email in cases:
                con.execute(
                    """INSERT INTO occurrences(case_number,occurrence_type_id,title,status,
                       due_date,owner_name,owner_email,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (number, kind, "Synthetic", status, due, owner, email,
                     "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"))

    def test_aggregates_by_owner_and_excludes_closed_and_future(self):
        rows = owner_escalations(self.db, date(2026, 11, 19))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["unassigned"], "YES")
        self.assertEqual(rows[0]["oldest_days_overdue"], 7)
        self.assertEqual(rows[1]["overdue_cases"], 2)
        self.assertEqual(rows[1]["oldest_days_overdue"], 9)
        self.assertEqual(rows[1]["case_numbers"], "SYN-1; SYN-2")

    def test_cli_csv(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main([str(self.db), "--as-of", "2026-11-19"]), 0)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["overdue_cases"], "2")

    def test_formula_injection_neutralized(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE occurrences SET owner_name='=HYPERLINK(1)' WHERE case_number='SYN-4'")
        out = io.StringIO()
        with redirect_stdout(out):
            main([str(self.db), "--as-of", "2026-11-19"])
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertTrue(any(row["owner_name"] == "'=HYPERLINK(1)" for row in rows))

    def test_read_only(self):
        before = self.db.read_bytes()
        owner_escalations(self.db, date(2026, 11, 19))
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_database_not_created(self):
        missing = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            owner_escalations(missing, date(2026, 11, 19))
        self.assertFalse(missing.exists())

    def test_invalid_due_date_rejected(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE occurrences SET due_date='not-a-date' WHERE case_number='SYN-1'")
        with self.assertRaisesRegex(ValueError, "SYN-1"):
            owner_escalations(self.db, date(2026, 11, 19))


if __name__ == "__main__":
    unittest.main()
