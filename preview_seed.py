from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ez_expedite.db import connect, init_db, set_setting, utcnow


def main() -> None:
    root = Path(__file__).resolve().parent
    instance = root / "instance"
    instance.mkdir(parents=True, exist_ok=True)
    db = instance / "ez_expedite.db"
    if db.exists():
        db.unlink()
    init_db(db)

    today = date.today()
    now = utcnow()

    with connect(db) as con:
        set_setting(con, "setup_complete", "1")
        set_setting(con, "multi_user_mode", "0")
        set_setting(con, "theme_accent", "#1F6FBC")
        set_setting(con, "theme_accent_strong", "#0B3A75")
        set_setting(con, "theme_background", "#090B0E")
        set_setting(con, "theme_panel", "#11161C")
        set_setting(con, "theme_card", "#171E26")
        set_setting(con, "theme_text", "#F4F7FB")
        set_setting(con, "theme_muted", "#9BA8B7")
        set_setting(con, "rma_role_csr_name", "Customer Service")
        set_setting(con, "rma_role_csr_email", "csr@example.com")
        set_setting(con, "rma_role_shipping_name", "Shipping")
        set_setting(con, "rma_role_shipping_email", "shipping@example.com")
        set_setting(con, "rma_role_quality_name", "Quality")
        set_setting(con, "rma_role_quality_email", "quality@example.com")

        rma_type = con.execute("SELECT id FROM occurrence_types WHERE name='RMA'").fetchone()[0]

        rows = [
            ("TEST-RMA-1001", "Example Customer A", "Surface defect", "RMA REVIEW", "Quality", "quality@example.com", -36, "Review disposition and confirm corrective action.", "Customer photos and inspection results received."),
            ("TEST-RMA-1002", "Example Customer B", "Missing hardware", "AWAITING CUSTOMER RETURN", "Shipping", "shipping@example.com", -22, "Confirm returned product receipt.", "Carrier tracking shows delivery expected this morning."),
            ("TEST-RMA-1003", "Example Customer C", "Dimension out", "RMA REVIEW", "Quality", "quality@example.com", -12, "Complete product review.", "Inspection is in progress; dimensional report attached."),
            ("TEST-RMA-1004", "Example Customer D", "Paint defect", "RETURN TO CUSTOMER", "Shipping", "shipping@example.com", -6, "Complete final inspection and shipment confirmation.", "Rework complete. Waiting for final inspection."),
            ("TEST-RMA-1005", "Example Customer E", "Wrong material", "INTAKE", "Customer Service", "csr@example.com", -2, "Complete intake fields.", "Customer contact information verified."),
            ("TEST-RMA-1006", "Example Customer F", "Forming issue", "AWAITING CUSTOMER RETURN", "Shipping", "shipping@example.com", -1, "Receive return and confirm hold-area placement.", "Return authorization sent to customer."),
            ("TEST-RMA-1007", "Example Customer G", "Weld defect", "RMA REVIEW", "Quality", "quality@example.com", 2, "Review product and issue work order when required.", "Awaiting internal review."),
            ("TEST-RMA-1008", "Example Customer H", "Packaging damage", "INTAKE", "Customer Service", "csr@example.com", 5, "Complete intake fields.", "Initial customer email received."),
        ]

        first_id = None
        for idx, (rma_no, customer, defect, stage, owner_name, owner_email, due_offset, next_action, note) in enumerate(rows, start=1):
            case_number = f"RMA-{today.year}-{idx:04d}"
            cur = con.execute(
                """INSERT INTO occurrences(
                   case_number,occurrence_type_id,title,description,source,customer,purchase_order,
                   owner_name,owner_email,priority,status,next_action,due_date,created_date,last_activity_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_number,
                    rma_type,
                    f"{rma_no} | {customer}",
                    defect,
                    "Synthetic UI preview",
                    customer,
                    f"PO-{9000+idx}",
                    owner_name,
                    owner_email,
                    "High" if due_offset < -7 else "Normal",
                    "INVESTIGATING",
                    next_action,
                    (today + timedelta(days=due_offset)).isoformat(),
                    (today - timedelta(days=45-idx)).isoformat(),
                    now,
                    now,
                    now,
                ),
            )
            oid = int(cur.lastrowid)
            if first_id is None:
                first_id = oid
            con.execute(
                """INSERT INTO rma_details(
                   occurrence_id,rma_number,rma_stage,defect_type,csr_name,contact_name,contact_phone,
                   received_from_customer,hold_area_confirmed,product_reviewed,work_order_required,
                   work_order_issued,final_quality_result,approved_to_ship,ready_to_ship,
                   shipped_to_customer,recovery_status,total_rework_cost,recovery_requested,recovery_received)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    oid,
                    rma_no,
                    stage,
                    defect,
                    "Customer Service",
                    "Example Contact",
                    "555-0100",
                    "YES" if stage != "INTAKE" else "",
                    1 if stage not in {"INTAKE"} else 0,
                    1 if stage in {"RMA REVIEW", "RETURN TO CUSTOMER", "COMPLETE"} else 0,
                    "NO" if stage == "RMA REVIEW" else "",
                    "",
                    "PASS" if stage in {"RETURN TO CUSTOMER", "COMPLETE"} else "",
                    "YES" if stage in {"RETURN TO CUSTOMER", "COMPLETE"} else "",
                    "YES" if stage in {"RETURN TO CUSTOMER", "COMPLETE"} else "",
                    0,
                    "NOT REQUIRED",
                    float(idx * 25),
                    0,
                    0,
                ),
            )
            con.execute(
                "INSERT INTO activities(occurrence_id,activity_type,detail,actor,created_at) VALUES(?,?,?,?,?)",
                (oid, "PROGRESS", note, owner_name, now),
            )

        # Give the first RMA a richer current workflow state for the detail preview.
        con.execute(
            """UPDATE rma_details SET product_reviewed=1,work_order_required='YES',work_order_issued='YES'
               WHERE occurrence_id=?""",
            (first_id,),
        )
        con.execute(
            "UPDATE occurrences SET work_order='WO-TEST-1001' WHERE id=?",
            (first_id,),
        )

    print(first_id or 1)


if __name__ == "__main__":
    main()
