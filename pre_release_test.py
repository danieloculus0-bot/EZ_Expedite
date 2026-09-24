from __future__ import annotations

import io
import tempfile
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

from ez_expedite.db import connect, init_db, set_setting
from ez_expedite.expediter import run_expeditor
from ez_expedite.importers import import_rma_workbook
from ez_expedite.web import create_app
import ez_expedite.routes_integrations as routes_integrations
import ez_expedite.routes_occurrence as routes_occurrence


RMA_HEADERS = [
    "Type","S.O. #","Job","P.O Rec #","W.O.","Rework W.O. #","Customer","Customer PO#","Supplier",
    "Part Number","Revision","Description","Quality No.","Customer NCR#","Qty Authorized","Qty Received",
    "Create Date","QC Due Date","Close Date","Receive Date","Department","Approved By","Employee","Created By",
    "Inspected By","Performed By","Received By","Responsible Empl.","Rejection Type","Discrepancy",
    "Containment Action Exists","Corrective Action Required","Corrective Action Completed","Item Class",
    "Original Qty","Work Center","Initial Work Center","Operation","Initial Operation","Disposition Type One",
    "Disposition Type Two","Disposition Type Three","Reject Type","Total Rework Cost","Sales Comment (RMA)",
    "Customer Discrepancy","Status","Disposition Completed","Qty Returned","Customer Complaint","Description",
]


class FakeM365:
    def __init__(self):
        self.teams = []
        self.mail = []
        self.messages = {
            "MSG-1": {
                "id": "MSG-1",
                "subject": "Customer complaint 123",
                "from": {"emailAddress": {"name": "Customer Person", "address": "customer@example.com"}},
                "receivedDateTime": "2026-09-24T10:00:00Z",
                "bodyPreview": "Parts arrived damaged. Please advise.",
                "webLink": "https://outlook.office.com/mail/test",
            }
        }

    def me(self):
        return {"id": "ME", "displayName": "Test User", "userPrincipalName": "test@example.com"}

    def send_teams_message(self, recipient, text):
        self.teams.append((recipient, text))
        return "TEAMMSG-1"

    def send_mail(self, to_address, subject, body):
        self.mail.append((to_address, subject, body))

    def recent_inbox(self, top=25):
        return list(self.messages.values())

    def message(self, message_id):
        return self.messages[message_id]


def build_rma_workbook(path: Path, count: int = 1200) -> None:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Sheet1")
    ws.append(RMA_HEADERS)
    opened = date(2026, 1, 1)
    for i in range(count):
        status = "Open" if i % 10 == 0 else "Closed"
        close_date = None if status == "Open" else opened + timedelta(days=5)
        due_date = opened + timedelta(days=7)
        row = [
            "WorkOrder",              # Type
            100000 + i,               # S.O. #
            f"JOB-{i:05d}",           # Job
            None,                     # P.O Rec #
            200000 + i,               # W.O.
            None,                     # Rework W.O. #
            f"Customer {i % 25}",      # Customer
            f"PO-{i:05d}",            # Customer PO#
            None,                     # Supplier
            f"PART-{i % 100:03d}",     # Part Number
            "A",                      # Revision
            f"Part description {i}",  # FIRST Description
            f"TEST-RMA-{i:06d}",      # Quality No. source-format alias
            f"NCR-{i:05d}",            # Customer NCR#
            10,                       # Qty Authorized
            10,                       # Qty Received
            opened,                   # Create Date
            due_date,                 # QC Due Date
            close_date,               # Close Date
            opened + timedelta(days=2),
            f"Dept {i % 8}",
            None,None,"Test User","NCR",None,None,
            f"Owner {i % 12}",
            "P",
            f"Discrepancy {i}",
            i % 3 == 0,
            i % 5 == 0,
            i % 5 != 0 or status == "Closed",
            "CLASS",
            10,
            f"WC-{i % 6}",
            None,None,None,
            "Rework" if i % 2 else "Use As Is",
            None,None,
            "Process / Product Nonconformity",
            float(i % 40) * 2.5,
            f"RMA comment {i}",
            f"Customer discrepancy {i}",
            status,
            status == "Closed",
            0,
            True,
            f"Trailing description {i}",  # SECOND Description
        ]
        assert len(row) == len(RMA_HEADERS)
        ws.append(row)
    wb.save(path)
    wb.close()


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        db = root / "pre_release.db"
        uploads = root / "uploads"
        tokens = root / "tokens.json"
        init_db(db)

        with connect(db) as con:
            set_setting(con, "setup_complete", "1")
            con.execute(
                "INSERT INTO occurrence_types(name,prefix,active,created_at) VALUES('PURCHASE REQUEST','PR',1,'2026-01-01T00:00:00Z')"
            )
            purchase_type = con.execute(
                "SELECT id FROM occurrence_types WHERE name='PURCHASE REQUEST'"
            ).fetchone()[0]
            con.execute(
                """INSERT INTO custom_field_defs(
                   occurrence_type_id,name,label,field_type,required,sort_order,active)
                   VALUES(?,?,?,?,?,?,1)""",
                (purchase_type, "requestor", "Requestor", "text", 1, 10),
            )
            con.execute(
                """INSERT INTO checklist_templates(occurrence_type_id,label,required,sort_order,active)
                   VALUES(?,?,?,?,1)""",
                (purchase_type, "Purchasing acknowledged", 1, 10),
            )

        app = create_app(
            {
                "TESTING": True,
                "DB_PATH": str(db),
                "UPLOAD_FOLDER": str(uploads),
                "TOKEN_CACHE": str(tokens),
            }
        )
        client = app.test_client()

        # 1. Synthetic RMA-format stress/synchronization test.
        rma_file = root / "synthetic_rma_compatibility.xlsx"
        build_rma_workbook(rma_file)
        with connect(db) as con:
            first = import_rma_workbook(con, rma_file, actor="Pre-release stress test")
            assert first == {"imported": 1200, "updated": 0, "skipped": 0}
            assert con.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0] == 1200
            assert con.execute("SELECT COUNT(*) FROM rma_details").fetchone()[0] == 1200
            assert con.execute("SELECT COUNT(*) FROM occurrences WHERE status!='CLOSED'").fetchone()[0] == 120
            first_rma = con.execute(
                "SELECT * FROM rma_details WHERE rma_number='TEST-RMA-000000'"
            ).fetchone()
            assert first_rma["rma_number"] == "TEST-RMA-000000"
            assert first_rma["part_description"] == "Part description 0", first_rma["part_description"]

            second = import_rma_workbook(con, rma_file, actor="Pre-release resync test")
            assert second == {"imported": 0, "updated": 1200, "skipped": 0}
            assert con.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0] == 1200
            assert con.execute(
                "SELECT COUNT(*) FROM (SELECT rma_number,COUNT(*) c FROM rma_details GROUP BY rma_number HAVING c>1)"
            ).fetchone()[0] == 0

        # 2. Universal non-RMA case creation.
        response = client.post(
            "/occurrence/new",
            data={
                "type_id": str(purchase_type),
                "title": "Expedite missing steel",
                "description": "Material is holding production.",
                "source": "Production meeting",
                "supplier": "Steel Supplier",
                "part_number": "MAT-001",
                "work_order": "WO-777",
                "purchase_order": "PO-888",
                "department": "Purchasing",
                "work_center": "Saw",
                "owner_name": "Buyer",
                "owner_email": "buyer@example.com",
                "priority": "High",
                "status": "NEW",
                "next_action": "Confirm supplier ship date",
                "due_date": (date.today() + timedelta(days=1)).isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code in (301, 302)
        with connect(db) as con:
            case = con.execute(
                "SELECT * FROM occurrences WHERE title='Expedite missing steel'"
            ).fetchone()
            assert case is not None
            oid = int(case["id"])
            checklist = con.execute(
                "SELECT * FROM checklist_items WHERE occurrence_id=?", (oid,)
            ).fetchone()
            field = con.execute(
                "SELECT * FROM custom_field_defs WHERE occurrence_type_id=? AND name='requestor'",
                (purchase_type,),
            ).fetchone()
            assert checklist is not None and field is not None

        # 3. Custom field save and owner Teams notification wiring.
        fake = FakeM365()
        old_occurrence_m365 = routes_occurrence.m365
        old_integration_m365 = routes_integrations.m365
        routes_occurrence.m365 = lambda: fake
        routes_integrations.m365 = lambda: fake
        try:
            response = client.post(
                f"/occurrence/{oid}",
                data={
                    "title": "Expedite missing steel",
                    "description": "Material is holding production.",
                    "source": "Production meeting",
                    "supplier": "Steel Supplier",
                    "part_number": "MAT-001",
                    "work_order": "WO-777",
                    "purchase_order": "PO-888",
                    "department": "Purchasing",
                    "work_center": "Saw",
                    "owner_name": "New Buyer",
                    "owner_email": "newbuyer@example.com",
                    "priority": "High",
                    "status": "INVESTIGATING",
                    "next_action": "Get confirmed truck date",
                    "due_date": (date.today() + timedelta(days=1)).isoformat(),
                    f"custom_{field['id']}": "Production Supervisor",
                    "notify_owner": "1",
                },
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            assert len(fake.teams) == 1
            assert fake.teams[0][0] == "newbuyer@example.com"

            with connect(db) as con:
                value = con.execute(
                    "SELECT value_text FROM custom_field_values WHERE occurrence_id=? AND field_def_id=?",
                    (oid, field["id"]),
                ).fetchone()
                assert value and value["value_text"] == "Production Supervisor"

            # 4. Checklist update and closure gating.
            response = client.post(
                f"/occurrence/{oid}/checklist",
                data={f"item_{checklist['id']}": "1", "actor": "Quality"},
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            response = client.get(f"/occurrence/{oid}/close")
            assert response.status_code == 200
            assert b"No automated blockers" in response.data

            # 5. Attachment round trip.
            response = client.post(
                f"/occurrence/{oid}/attachment",
                data={"attachment": (io.BytesIO(b"real attachment test"), "evidence.txt"), "actor": "Quality"},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            with connect(db) as con:
                attachment_id = con.execute(
                    "SELECT id FROM attachments WHERE occurrence_id=? AND file_name='evidence.txt'",
                    (oid,),
                ).fetchone()[0]
            response = client.get(f"/attachment/{attachment_id}")
            assert response.status_code == 200
            assert response.data == b"real attachment test"

            # 6. ERP/external record link.
            response = client.post(
                f"/occurrence/{oid}/external",
                data={
                    "system_name": "JobBOSS2",
                    "entity_type": "Work Order",
                    "external_id": "WO-777",
                    "external_url": "https://example.invalid/job/WO-777",
                    "note": "Pre-release test record",
                },
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            with connect(db) as con:
                ref = con.execute(
                    "SELECT * FROM external_refs WHERE occurrence_id=? AND external_id='WO-777'",
                    (oid,),
                ).fetchone()
                assert ref and ref["system_name"] == "JobBOSS2"

            # 7. Outlook send wiring.
            response = client.post(
                f"/occurrence/{oid}/email",
                data={"to": "supplier@example.com", "subject": "Need ship date", "body": "Please confirm."},
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            assert fake.mail == [("supplier@example.com", "Need ship date", "Please confirm.")]

            # 8. Outlook inbox to arbitrary occurrence type and duplicate prevention.
            response = client.get("/mail/inbox")
            assert response.status_code == 200
            assert b"Customer complaint 123" in response.data
            response = client.post(
                "/mail/create",
                data={"message_id": "MSG-1", "type_id": str(purchase_type)},
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            with connect(db) as con:
                email_case = con.execute(
                    "SELECT occurrence_id FROM occurrence_emails WHERE message_id='MSG-1'"
                ).fetchone()
                assert email_case is not None
                email_oid = int(email_case["occurrence_id"])
                linked_type = con.execute(
                    """SELECT t.name FROM occurrences o JOIN occurrence_types t ON t.id=o.occurrence_type_id
                       WHERE o.id=?""",
                    (email_oid,),
                ).fetchone()[0]
                assert linked_type == "PURCHASE REQUEST"
            response = client.post(
                "/mail/create",
                data={"message_id": "MSG-1", "type_id": str(purchase_type)},
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            with connect(db) as con:
                assert con.execute(
                    "SELECT COUNT(*) FROM occurrence_emails WHERE message_id='MSG-1'"
                ).fetchone()[0] == 1

            # 9. Due reminder and duplicate suppression.
            with connect(db) as con:
                result = run_expeditor(
                    con,
                    notify_teams=fake.send_teams_message,
                    today=date.today(),
                )
                assert result["sent"] >= 1
                sent_after_first = len(fake.teams)
                result2 = run_expeditor(
                    con,
                    notify_teams=fake.send_teams_message,
                    today=date.today(),
                )
                assert result2["sent"] == 0
                assert len(fake.teams) == sent_after_first

            # 10. Actual closure after required fields/checklist are complete.
            response = client.post(
                f"/occurrence/{oid}/close",
                data={"actor": "Quality"},
                follow_redirects=False,
            )
            assert response.status_code in (301, 302)
            with connect(db) as con:
                closed = con.execute("SELECT status,closed_date FROM occurrences WHERE id=?", (oid,)).fetchone()
                assert closed["status"] == "CLOSED"
                assert closed["closed_date"]

        finally:
            routes_occurrence.m365 = old_occurrence_m365
            routes_integrations.m365 = old_integration_m365

        print("EZ Expedite pre-release functional test passed")


if __name__ == "__main__":
    main()
