from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

from ez_expedite.db import connect, generic_close_blockers, init_db
from ez_expedite.expediter import run_expeditor
from ez_expedite.generic_import import import_generic_file
from ez_expedite.importers import RMA_NUMBER_ALIASES
from ez_expedite.web import create_app


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = root / "test.db"
        uploads = root / "uploads"
        cache = root / "tokens.json"
        init_db(db)

        with connect(db) as con:
            assert con.execute("SELECT name FROM occurrence_types WHERE name='RMA'").fetchone()[0] == "RMA"
            assert con.execute("SELECT value FROM settings WHERE key='setup_complete'").fetchone()[0] == "0"
            con.execute(
                "INSERT INTO occurrence_types(name,prefix,active,created_at) VALUES('PURCHASE REQUEST','PR',1,'2026-01-01T00:00:00Z')"
            )
            type_id = con.execute("SELECT id FROM occurrence_types WHERE name='PURCHASE REQUEST'").fetchone()[0]
            con.execute(
                """INSERT INTO custom_field_defs(
                   occurrence_type_id,name,label,field_type,required,sort_order,active)
                   VALUES(?,?,?,?,?,?,1)""",
                (type_id, "requestor", "Requestor", "text", 1, 10),
            )
            con.execute(
                """INSERT INTO checklist_templates(occurrence_type_id,label,required,sort_order,active)
                   VALUES(?,?,?,?,1)""",
                (type_id, "Purchasing acknowledged", 1, 10),
            )

        app = create_app(
            {
                "TESTING": True,
                "DB_PATH": str(db),
                "UPLOAD_FOLDER": str(uploads),
                "TOKEN_CACHE": str(cache),
            }
        )
        client = app.test_client()
        assert client.get("/").status_code in (301, 302)
        assert client.get("/setup").status_code == 200
        assert client.get("/health").json["status"] == "ok"

        with connect(db) as con:
            con.execute("UPDATE settings SET value='1' WHERE key='setup_complete'")
            con.execute("UPDATE settings SET value='0' WHERE key='multi_user_mode'")

        assert client.get("/").status_code == 200
        assert client.get("/occurrence/new").status_code == 200
        assert client.get("/types").status_code == 200
        assert client.get(f"/type/{type_id}").status_code == 200
        assert client.get("/import/rma").status_code == 200
        assert client.get("/import/generic").status_code == 200
        assert client.get("/systems").status_code == 200

        response = client.post(
            "/occurrence/new",
            data={
                "type_id": str(type_id),
                "title": "Buy replacement inspection light",
                "owner_name": "Buyer",
                "owner_email": "buyer@example.com",
                "due_date": (date.today() - timedelta(days=1)).isoformat(),
                "next_action": "Place PO",
            },
            follow_redirects=False,
        )
        assert response.status_code in (301, 302)

        with connect(db) as con:
            occurrence = con.execute(
                "SELECT * FROM occurrences WHERE title='Buy replacement inspection light'"
            ).fetchone()
            assert occurrence is not None
            oid = occurrence["id"]
            assert con.execute(
                "SELECT COUNT(*) FROM checklist_items WHERE occurrence_id=?", (oid,)
            ).fetchone()[0] == 1
            blockers = generic_close_blockers(con, oid)
            assert any("Requestor" in blocker for blocker in blockers)
            assert any("Purchasing acknowledged" in blocker for blocker in blockers)

            sent = []
            result = run_expeditor(
                con,
                notify_teams=lambda recipient, message: sent.append((recipient, message)),
                today=date.today(),
            )
            assert result["digests_sent"] == 1
            assert sent and sent[0][0] == "buyer@example.com"
            result2 = run_expeditor(
                con,
                notify_teams=lambda recipient, message: sent.append((recipient, message)),
                today=date.today(),
            )
            assert result2["digests_sent"] == 0

        workbook_path = root / "generic.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["Ticket ID", "Subject", "Assigned Email", "Due Date", "Department"])
        ws.append(["JB-1001", "Expedite steel PO", "buyer2@example.com", date.today(), "Purchasing"])
        wb.save(workbook_path)

        with connect(db) as con:
            result = import_generic_file(
                con,
                workbook_path,
                type_id,
                {
                    "title": "Subject",
                    "owner_email": "Assigned Email",
                    "due_date": "Due Date",
                    "department": "Department",
                },
                external_system="JobBOSS2 Export",
                external_id_column="Ticket ID",
            )
            assert result["created"] == 1
            result = import_generic_file(
                con,
                workbook_path,
                type_id,
                {
                    "title": "Subject",
                    "owner_email": "Assigned Email",
                    "due_date": "Due Date",
                    "department": "Department",
                },
                external_system="JobBOSS2 Export",
                external_id_column="Ticket ID",
            )
            assert result["updated"] == 1

        assert "Quality No." in RMA_NUMBER_ALIASES
        assert "RMA Number" in RMA_NUMBER_ALIASES
        print("EZ Expedite smoke test passed")


if __name__ == "__main__":
    main()
