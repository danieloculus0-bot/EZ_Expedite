from __future__ import annotations

import csv
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from ez_expedite.db import init_db
from ez_expedite.rma_readiness_report import main, readiness_rows


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.db"
        init_db(self.path)
        with closing(sqlite3.connect(self.path)) as con, con:
            kind = con.execute("SELECT id FROM occurrence_types WHERE name='RMA'").fetchone()[0]
            for number, status, stage in (
                ("SYN-OPEN", "NEW", "INTAKE"),
                ("SYN-CLOSED", "CLOSED", "INTAKE"),
                ("SYN-FINAL", "READY TO CLOSE", "COMPLETE"),
            ):
                cursor = con.execute(
                    """INSERT INTO occurrences(case_number,occurrence_type_id,title,
                       status,created_at,updated_at) VALUES(?,?,?,?,?,?)""",
                    (number, kind, "Synthetic", status,
                     "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"),
                )
                con.execute("INSERT INTO rma_details(occurrence_id,rma_stage) VALUES(?,?)",
                            (cursor.lastrowid, stage))

    def test_open_queue_and_blockers(self):
        rows = readiness_rows(self.path)
        self.assertEqual([r["case_number"] for r in rows], ["SYN-FINAL", "SYN-OPEN"])
        self.assertEqual([r["ready"] for r in rows], ["NO", "NO"])
        self.assertIn("authorized workflow", rows[0]["blockers"])
        self.assertGreater(rows[1]["blocker_count"], 0)

    def test_csv_formula_guard(self):
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("UPDATE occurrences SET case_number='=1+1' WHERE case_number='SYN-OPEN'")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.path)]), 0)
        rows = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(rows[0]["case_number"], "'=1+1")

    def test_read_only_and_missing_db(self):
        before = self.path.read_bytes()
        readiness_rows(self.path)
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(FileNotFoundError):
            readiness_rows(Path(self.temp.name) / "missing.db")


if __name__ == "__main__":
    unittest.main()
