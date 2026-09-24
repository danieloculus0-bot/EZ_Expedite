from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from .db import log_activity, utcnow

Notifier = Callable[[str, str], None]


def reminder_rule(due: date, today: date) -> tuple[str, str] | None:
    delta = (due - today).days
    if delta == 1:
        return "UPCOMING_1D", "is due tomorrow"
    if delta == 0:
        return "DUE_TODAY", "is due today"
    overdue = -delta
    if overdue in {1, 3, 7} or (overdue > 7 and overdue % 7 == 0):
        return f"OVERDUE_{overdue}D", f"is {overdue} day{'s' if overdue != 1 else ''} overdue"
    return None


def run_expeditor(con, notify_teams: Notifier | None = None, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    rows = con.execute(
        """SELECT o.*,t.name type_name
           FROM occurrences o
           JOIN occurrence_types t ON t.id=o.occurrence_type_id
           WHERE o.status!='CLOSED'"""
    ).fetchall()
    result = {"checked": 0, "sent": 0, "unassigned": 0, "due_without_action": 0, "errors": 0}

    for row in rows:
        result["checked"] += 1
        if not (row["owner_name"] or row["owner_email"]):
            result["unassigned"] += 1
            if row["status"] == "NEW":
                con.execute(
                    "UPDATE occurrences SET status='ASSIGNMENT REQUIRED',updated_at=? WHERE id=?",
                    (utcnow(), row["id"]),
                )

        if row["due_date"] and not str(row["next_action"] or "").strip():
            result["due_without_action"] += 1

        if not row["due_date"] or not row["owner_email"] or notify_teams is None:
            continue
        try:
            due = datetime.strptime(row["due_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        rule = reminder_rule(due, today)
        if not rule:
            continue
        rule_key, phrase = rule
        recipient = row["owner_email"].strip().lower()
        exists = con.execute(
            """SELECT 1 FROM notifications
               WHERE occurrence_id=? AND channel='TEAMS' AND rule_key=?
                 AND COALESCE(due_date_snapshot,'')=COALESCE(?, '')
                 AND recipient=?""",
            (row["id"], rule_key, row["due_date"], recipient),
        ).fetchone()
        if exists:
            continue

        message = (
            f"EZ Expedite: {row['case_number']} {phrase}\n"
            f"Type: {row['type_name']}\n"
            f"Occurrence: {row['title']}\n"
            f"Next action: {row['next_action'] or 'Not defined'}\n"
            f"Due: {row['due_date']}"
        )
        try:
            notify_teams(recipient, message)
            con.execute(
                """INSERT INTO notifications(
                   occurrence_id,channel,rule_key,due_date_snapshot,recipient,sent_at,detail)
                   VALUES(?,?,?,?,?,?,?)""",
                (row["id"], "TEAMS", rule_key, row["due_date"], recipient, utcnow(), phrase),
            )
            log_activity(con, row["id"], "EXPEDITE", f"Teams reminder sent: {phrase}.", "EZ Expedite")
            result["sent"] += 1
        except Exception as exc:
            log_activity(con, row["id"], "EXPEDITE ERROR", f"Reminder failed: {exc}", "EZ Expedite")
            result["errors"] += 1
    return result
