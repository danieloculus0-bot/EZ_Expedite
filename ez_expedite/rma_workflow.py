from __future__ import annotations

from dataclasses import dataclass

from .db import get_setting, log_activity, utcnow


@dataclass(frozen=True)
class RMAStage:
    key: str
    label: str
    role_key: str
    role_label: str
    action: str


STAGES = [
    RMAStage("INTAKE", "Intake", "csr", "CSR", "Complete RMA intake and initiate the notification."),
    RMAStage(
        "AWAITING CUSTOMER RETURN",
        "Product Returned to WMF",
        "shipping",
        "Shipping Clerk",
        "Receive the customer return and place it in the RMA hold area.",
    ),
    RMAStage(
        "RMA REVIEW",
        "RMA Review",
        "quality",
        "Quality Manager",
        "Review the returned product and determine whether a work order is required.",
    ),
    RMAStage(
        "RETURN TO CUSTOMER",
        "Product Returned to Customer",
        "shipping",
        "Shipping Clerk",
        "Complete final quality approval and return the product to the customer.",
    ),
    RMAStage(
        "COMPLETE",
        "Complete",
        "shipping",
        "Shipping Clerk",
        "Verify the record is complete and close the occurrence.",
    ),
]

_STAGE_BY_KEY = {stage.key: stage for stage in STAGES}
_NEXT = {
    "INTAKE": "AWAITING CUSTOMER RETURN",
    "AWAITING CUSTOMER RETURN": "RMA REVIEW",
    "RMA REVIEW": "RETURN TO CUSTOMER",
    "RETURN TO CUSTOMER": "COMPLETE",
}
_STATUS_BY_STAGE = {
    "INTAKE": "NEW",
    "AWAITING CUSTOMER RETURN": "AWAITING MATERIAL",
    "RMA REVIEW": "INVESTIGATING",
    "RETURN TO CUSTOMER": "AWAITING INTERNAL ACTION",
    "COMPLETE": "READY TO CLOSE",
}


def stage_info(stage_key: str | None) -> RMAStage:
    return _STAGE_BY_KEY.get(stage_key or "", STAGES[0])


def stage_index(stage_key: str | None) -> int:
    for index, stage in enumerate(STAGES):
        if stage.key == stage_key:
            return index
    return 0


def _present(value) -> bool:
    return bool(str(value or "").strip())


def stage_blockers(row) -> list[str]:
    stage = row["rma_stage"] or "INTAKE"
    blockers: list[str] = []

    if stage == "INTAKE":
        required = [
            ("RMA Number", row["rma_number"]),
            ("Defect Type", row["defect_type"]),
            ("CSR Name", row["csr_name"]),
            ("PO #", row["purchase_order"]),
            ("Customer Name", row["customer"]),
            ("Contact Name", row["contact_name"]),
            ("Contact #", row["contact_phone"]),
        ]
        blockers.extend(f"{label} is required." for label, value in required if not _present(value))
        if not _present(row["description"]) and not _present(row["sales_comment"]):
            blockers.append("Notes are required.")

    elif stage == "AWAITING CUSTOMER RETURN":
        decision = str(row["received_from_customer"] or "").upper()
        if decision != "YES":
            blockers.append(
                "Customer product must be received before advancing."
                if decision == "NO"
                else "Received from Customer must be answered YES or NO."
            )
        if not row["hold_area_confirmed"]:
            blockers.append("RMA hold-area placement must be confirmed.")

    elif stage == "RMA REVIEW":
        if not row["product_reviewed"]:
            blockers.append("Product review must be completed.")
        required = str(row["work_order_required"] or "").upper()
        if required not in {"YES", "NO"}:
            blockers.append("Work Order Required must be answered YES or NO.")
        if required == "YES":
            if str(row["work_order_issued"] or "").upper() != "YES":
                blockers.append("A required work order has not been issued.")
            if not _present(row["work_order"]):
                blockers.append("Work Order # is required when a work order is needed.")

    elif stage == "RETURN TO CUSTOMER":
        result = str(row["final_quality_result"] or "").upper()
        if result not in {"PASS", "FAIL"}:
            blockers.append("Final Quality Inspection must be PASS or FAIL.")
        elif result == "FAIL":
            blockers.append("Final Quality Inspection failed. Return the RMA to review.")
        if str(row["approved_to_ship"] or "").upper() != "YES":
            blockers.append("Product is not approved to ship.")
        if str(row["ready_to_ship"] or "").upper() != "YES":
            blockers.append("Product is not marked ready to ship.")
        if not row["shipped_to_customer"]:
            blockers.append("Return shipment to the customer has not been confirmed.")

    return blockers


def _role_settings(con, role_key: str) -> tuple[str, str]:
    return (
        get_setting(con, f"rma_role_{role_key}_name", ""),
        get_setting(con, f"rma_role_{role_key}_email", ""),
    )


def assign_stage_owner(con, occurrence_id: int, stage_key: str) -> tuple[str, str]:
    stage = stage_info(stage_key)
    name, email = _role_settings(con, stage.role_key)
    if name or email:
        con.execute(
            "UPDATE occurrences SET owner_name=?,owner_email=?,updated_at=? WHERE id=?",
            (name, email, utcnow(), occurrence_id),
        )
    return name, email


def notification_recipients(con, primary_email: str = "") -> list[str]:
    values = [primary_email]
    for key in ("quality", "operations", "customer_service", "design"):
        values.append(get_setting(con, f"rma_cc_{key}", ""))
    recipients: list[str] = []
    seen = set()
    for value in values:
        for part in str(value or "").replace(";", ",").split(","):
            email = part.strip().lower()
            if email and email not in seen:
                seen.add(email)
                recipients.append(email)
    return recipients


def stage_message(row, new_stage: str, owner_name: str, owner_email: str) -> str:
    stage = stage_info(new_stage)
    primary = owner_name or owner_email or stage.role_label
    return (
        f"EZ Expedite - ACTION REQUIRED\n"
        f"RMA: {row['rma_number'] or row['case_number']}\n"
        f"Stage: {stage.label}\n"
        f"WMF Primary: {primary}\n"
        f"Customer: {row['customer'] or 'Not entered'}\n"
        f"Defect: {row['defect_type'] or row['discrepancy'] or 'Not entered'}\n"
        f"PO: {row['purchase_order'] or 'Not entered'}\n"
        f"Next Action: {stage.action}\n"
        f"Due: {row['due_date'] or 'Not assigned'}"
    )


def advance_rma(con, occurrence_id: int, actor: str = "") -> dict:
    row = con.execute(
        """SELECT o.*,r.*
           FROM occurrences o
           JOIN rma_details r ON r.occurrence_id=o.id
           WHERE o.id=?""",
        (occurrence_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "blockers": ["RMA occurrence not found."]}

    current = row["rma_stage"] or "INTAKE"

    if current == "RETURN TO CUSTOMER" and str(row["final_quality_result"] or "").upper() == "FAIL":
        new_stage = "RMA REVIEW"
        con.execute(
            "UPDATE rma_details SET rma_stage=? WHERE occurrence_id=?",
            (new_stage, occurrence_id),
        )
        con.execute(
            "UPDATE occurrences SET status=?,updated_at=? WHERE id=?",
            (_STATUS_BY_STAGE[new_stage], utcnow(), occurrence_id),
        )
        owner_name, owner_email = assign_stage_owner(con, occurrence_id, new_stage)
        log_activity(
            con,
            occurrence_id,
            "RMA STAGE",
            "Final quality inspection failed. RMA returned to RMA Review.",
            actor,
        )
        refreshed = con.execute(
            """SELECT o.*,r.* FROM occurrences o JOIN rma_details r ON r.occurrence_id=o.id WHERE o.id=?""",
            (occurrence_id,),
        ).fetchone()
        return {
            "ok": True,
            "new_stage": new_stage,
            "owner_name": owner_name,
            "owner_email": owner_email,
            "message": stage_message(refreshed, new_stage, owner_name, owner_email),
        }

    blockers = stage_blockers(row)
    if blockers:
        return {"ok": False, "blockers": blockers}

    new_stage = _NEXT.get(current)
    if not new_stage:
        return {"ok": False, "blockers": ["This RMA workflow is already complete."]}

    con.execute(
        "UPDATE rma_details SET rma_stage=? WHERE occurrence_id=?",
        (new_stage, occurrence_id),
    )
    con.execute(
        "UPDATE occurrences SET status=?,updated_at=? WHERE id=?",
        (_STATUS_BY_STAGE[new_stage], utcnow(), occurrence_id),
    )
    owner_name, owner_email = assign_stage_owner(con, occurrence_id, new_stage)
    log_activity(
        con,
        occurrence_id,
        "RMA STAGE",
        f"RMA advanced from {stage_info(current).label} to {stage_info(new_stage).label}.",
        actor,
    )
    refreshed = con.execute(
        """SELECT o.*,r.* FROM occurrences o JOIN rma_details r ON r.occurrence_id=o.id WHERE o.id=?""",
        (occurrence_id,),
    ).fetchone()
    return {
        "ok": True,
        "new_stage": new_stage,
        "owner_name": owner_name,
        "owner_email": owner_email,
        "message": stage_message(refreshed, new_stage, owner_name, owner_email),
    }


def stage_rail(stage_key: str | None) -> list[dict]:
    current_index = stage_index(stage_key)
    return [
        {
            "key": stage.key,
            "label": stage.label,
            "role_label": stage.role_label,
            "state": "done" if index < current_index else "current" if index == current_index else "future",
        }
        for index, stage in enumerate(STAGES)
    ]
