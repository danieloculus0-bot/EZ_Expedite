from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, request, send_file, url_for
from werkzeug.utils import secure_filename

from .db import (
    connect,
    ensure_checklist_items,
    generic_close_blockers,
    get_setting,
    log_activity,
    set_custom_value,
    utcnow,
)
from .helpers import PRIORITIES, STATUSES, db_path, e, fnum, m365, page, profile, truth
from .m365 import M365Error
from .rma_workflow import (
    advance_rma,
    can_advance,
    stage_delegates,
    stage_info,
    stage_rail,
)

bp = Blueprint("occurrence", __name__)


def _custom_control(field) -> str:
    name = f"custom_{field['id']}"
    value = field["value_text"] or ""
    kind = field["field_type"]
    if kind == "textarea":
        control = f"<textarea name='{name}'>{e(value)}</textarea>"
    elif kind == "select":
        options = [x.strip() for x in (field["options_text"] or "").split("|") if x.strip()]
        control = "<select name='" + name + "'><option value=''></option>" + "".join(
            f"<option value='{e(x)}' {'selected' if value == x else ''}>{e(x)}</option>" for x in options
        ) + "</select>"
    elif kind == "checkbox":
        control = f"<input type='checkbox' name='{name}' value='1' {'checked' if str(value).lower() in {'1','true','yes','on'} else ''}>"
    else:
        html_type = kind if kind in {"number", "date", "email", "url"} else "text"
        control = f"<input type='{html_type}' name='{name}' value='{e(value)}'>"
    req = " *" if field["required"] else ""
    return f"<label>{e(field['label'])}{req}{control}</label>"



def _user_identity() -> tuple[str, str]:
    person = profile() or {}
    email = str(person.get("mail") or person.get("userPrincipalName") or "").strip().lower()
    name = str(person.get("displayName") or email).strip()
    return name, email


def _rma_write_allowed(con, oid: int) -> bool:
    row = con.execute(
        """SELECT t.name type_name,r.rma_stage
           FROM occurrences o
           JOIN occurrence_types t ON t.id=o.occurrence_type_id
           LEFT JOIN rma_details r ON r.occurrence_id=o.id
           WHERE o.id=?""",
        (oid,),
    ).fetchone()
    if not row or row["type_name"] != "RMA":
        return True
    if get_setting(con, "multi_user_mode", "1") != "1":
        return True
    _name, email = _user_identity()
    return can_advance(con, row["rma_stage"] or "INTAKE", email)


def _deny_rma_write(con, oid: int) -> bool:
    if _rma_write_allowed(con, oid):
        return False
    flash("This RMA is read only for the connected user.")
    return True


def _segmented(name: str, options: list[str], selected: str = "") -> str:
    return "<div class='segmented'>" + "".join(
        f"<label><input type='radio' name='{e(name)}' value='{e(option)}' {'checked' if str(selected or '').upper()==option.upper() else ''}><span>{e(option)}</span></label>"
        for option in options
    ) + "</div>"


def _rma_action_fields(row) -> str:
    stage = row["rma_stage"] or "INTAKE"
    if stage == "INTAKE":
        return f"""<div class='action-fields'>
        <label>RMA Number<input name='rma_number' value='{e(row["rma_number"])}' required></label>
        <label>Defect Type<input name='defect_type' value='{e(row["defect_type"])}' required></label>
        <label>CSR Name<input name='csr_name' value='{e(row["csr_name"])}' required></label>
        <label>PO #<input name='purchase_order' value='{e(row["purchase_order"])}' required></label>
        <label>Customer Name<input name='customer' value='{e(row["customer"])}' required></label>
        <label>Contact Name<input name='contact_name' value='{e(row["contact_name"])}' required></label>
        <label>Contact #<input name='contact_phone' value='{e(row["contact_phone"])}' required></label>
        <label class='wide'>Notes<textarea name='notes' required>{e(row["description"])}</textarea></label>
        </div>"""
    if stage == "AWAITING CUSTOMER RETURN":
        return f"""<div class='action-fields'>
        <label>Received from Customer{_segmented("received_from_customer", ["YES","NO"], row["received_from_customer"])}</label>
        <label>Receive Date<input type='date' name='receive_date' value='{e(row["receive_date"])}'></label>
        <label><input type='checkbox' name='hold_area_confirmed' value='1' {'checked' if row["hold_area_confirmed"] else ''}> RMA Hold Area confirmed</label>
        </div>"""
    if stage == "RMA REVIEW":
        return f"""<div class='action-fields'>
        <label><input type='checkbox' name='product_reviewed' value='1' {'checked' if row["product_reviewed"] else ''}> Product reviewed</label>
        <label>Work Order Required{_segmented("work_order_required", ["YES","NO"], row["work_order_required"])}</label>
        <label>Work Order Issued{_segmented("work_order_issued", ["YES","NO"], row["work_order_issued"])}</label>
        <label>Work Order #<input name='work_order' value='{e(row["work_order"])}'></label>
        </div>"""
    if stage == "RETURN TO CUSTOMER":
        return f"""<div class='action-fields'>
        <label>Final Quality Inspection{_segmented("final_quality_result", ["PASS","FAIL"], row["final_quality_result"])}</label>
        <label>Approved to Ship{_segmented("approved_to_ship", ["YES","NO"], row["approved_to_ship"])}</label>
        <label>Ready to Ship{_segmented("ready_to_ship", ["YES","NO"], row["ready_to_ship"])}</label>
        <label><input type='checkbox' name='shipped_to_customer' value='1' {'checked' if row["shipped_to_customer"] else ''}> Shipped to Customer</label>
        <label>Returned / Shipped Date<input type='date' name='returned_to_customer_date' value='{e(row["returned_to_customer_date"])}'></label>
        </div>"""
    return "<div class='notice'>Workflow complete.</div>"


def _rma_workflow_ui(row, allowed: bool, delegates: list[dict]) -> str:
    rail = "".join(
        f"""<div class='stage-step {item["state"]}'><span class='stage-num'>Stage {i}</span>
        <strong>{e(item["label"])}</strong><small>{e(item["role_label"])}</small></div>"""
        for i, item in enumerate(stage_rail(row["rma_stage"]), start=1)
    )
    stage = stage_info(row["rma_stage"])
    chips = "".join(
        f"<span class='delegate-chip'>{e(d['name'] or d['email'])}</span>" for d in delegates
    ) or "<span class='delegate-chip'>No primary delegate configured</span>"
    permission = "Action Required" if allowed else "Read Only"
    form = ""
    if allowed and stage.key != "COMPLETE":
        form = f"""<form method='post' action='/occurrence/{row["id"]}/rma/action'>
          {_rma_action_fields(row)}
          <label class='wide' style='margin-top:12px'>Progress Note<textarea name='progress_note'></textarea></label>
          <div class='toolbar'><button>Complete / Advance</button></div>
        </form>"""
    elif stage.key != "COMPLETE":
        form = f"""<div class='action-fields'>{_rma_action_fields(row)}</div>"""
        form = form.replace("<input ", "<input disabled ").replace("<textarea ", "<textarea disabled ").replace("<select ", "<select disabled ")
    return f"""<div class='stage-rail'>{rail}</div>
    <div class='action-card {'readonly' if not allowed else ''}'>
      <div class='section-head'><div><div class='kicker'>{e(permission)}</div><h2 style='margin:4px 0 0'>{e(stage.label)}</h2></div>
      <span class='status'>{e(stage.role_label)}</span></div>
      <div class='action-meta'><span>Primary:</span><div class='delegate-list'>{chips}</div></div>
      {form}
    </div>"""


@bp.route("/occurrence/<int:oid>", methods=["GET", "POST"])
def occurrence(oid):
    with connect(db_path()) as con:
        base = con.execute(
            """SELECT o.*,t.name type_name,r.*
               FROM occurrences o
               JOIN occurrence_types t ON t.id=o.occurrence_type_id
               LEFT JOIN rma_details r ON r.occurrence_id=o.id
               WHERE o.id=?""",
            (oid,),
        ).fetchone()
        if not base:
            return page("Not found", "<div class='panel'>Occurrence not found.</div>"), 404
        ensure_checklist_items(con, oid, base["occurrence_type_id"])

        custom = con.execute(
            """SELECT d.*,v.value_text FROM custom_field_defs d
               LEFT JOIN custom_field_values v ON v.field_def_id=d.id AND v.occurrence_id=?
               WHERE d.occurrence_type_id=? AND d.active=1 ORDER BY d.sort_order,d.id""",
            (oid, base["occurrence_type_id"]),
        ).fetchall()

        if request.method == "POST":
            if _deny_rma_write(con, oid):
                return redirect(url_for("occurrence.occurrence", oid=oid))
            is_rma = base["type_name"] == "RMA"
            old_owner = base["owner_email"]
            owner = base["owner_email"] if is_rma else request.form.get("owner_email", "").strip()
            owner_name = base["owner_name"] if is_rma else request.form.get("owner_name", "")
            status_value = base["status"] if is_rma else request.form.get("status", "NEW")
            next_action_value = base["next_action"] if is_rma else request.form.get("next_action", "")
            now = utcnow()
            con.execute(
                """UPDATE occurrences SET
                   title=?,description=?,source=?,customer=?,supplier=?,part_number=?,revision=?,work_order=?,
                   sales_order=?,purchase_order=?,department=?,work_center=?,owner_name=?,owner_email=?,priority=?,
                   status=?,next_action=?,due_date=?,updated_at=? WHERE id=?""",
                (
                    request.form.get("title", ""),
                    request.form.get("description", ""),
                    request.form.get("source", ""),
                    request.form.get("customer", ""),
                    request.form.get("supplier", ""),
                    request.form.get("part_number", ""),
                    request.form.get("revision", ""),
                    request.form.get("work_order", ""),
                    request.form.get("sales_order", ""),
                    request.form.get("purchase_order", ""),
                    request.form.get("department", ""),
                    request.form.get("work_center", ""),
                    owner_name,
                    owner,
                    request.form.get("priority", "Normal"),
                    status_value,
                    next_action_value,
                    request.form.get("due_date") or None,
                    now,
                    oid,
                ),
            )
            for field in custom:
                form_name = f"custom_{field['id']}"
                value = "1" if field["field_type"] == "checkbox" and request.form.get(form_name) else request.form.get(form_name, "")
                set_custom_value(con, oid, field["id"], value)

            if base["type_name"] == "RMA":
                con.execute(
                    """UPDATE rma_details SET rma_number=?,quality_no=?,customer_ncr=?,discrepancy=?,containment_required=?,
                       containment_complete=?,corrective_action_required=?,corrective_action_complete=?,disposition_complete=?,
                       total_rework_cost=?,scrap_cost=?,freight_cost=?,outside_processing_cost=?,recovery_requested=?,
                       recovery_received=?,recovery_status=?,recovery_owner=?,credit_memo_number=?,debit_memo_number=?,
                       sales_comment=?,customer_discrepancy=? WHERE occurrence_id=?""",
                    (
                        request.form.get("rma_number") or None,
                        request.form.get("quality_no") or None,
                        request.form.get("customer_ncr") or None,
                        request.form.get("discrepancy") or None,
                        truth(request.form.get("containment_required")),
                        truth(request.form.get("containment_complete")),
                        truth(request.form.get("corrective_action_required")),
                        truth(request.form.get("corrective_action_complete")),
                        truth(request.form.get("disposition_complete")),
                        fnum(request.form.get("total_rework_cost")),
                        fnum(request.form.get("scrap_cost")),
                        fnum(request.form.get("freight_cost")),
                        fnum(request.form.get("outside_processing_cost")),
                        fnum(request.form.get("recovery_requested")),
                        fnum(request.form.get("recovery_received")),
                        request.form.get("recovery_status", "NOT REQUIRED"),
                        request.form.get("recovery_owner") or None,
                        request.form.get("credit_memo_number") or None,
                        request.form.get("debit_memo_number") or None,
                        request.form.get("sales_comment") or None,
                        request.form.get("customer_discrepancy") or None,
                        oid,
                    ),
                )
            log_activity(con, oid, "UPDATE", "Occurrence updated.", request.form.get("owner_name", ""))

            if request.form.get("notify_owner") and owner and owner != old_owner:
                try:
                    m365().send_teams_message(
                        owner,
                        f"""{base['case_number']} assigned to you
Type: {base['type_name']}
Occurrence: {request.form.get('title','')}
Customer: {request.form.get('customer','')}
Part: {request.form.get('part_number','')}
Due: {request.form.get('due_date','')}
Next action: {request.form.get('next_action','')}""",
                    )
                    log_activity(con, oid, "TEAMS", "Owner assignment notification sent.", request.form.get("owner_name", ""))
                except M365Error as ex:
                    flash(f"Saved, but Teams notification failed: {ex}")
            return redirect(url_for("occurrence.occurrence", oid=oid))

        row = con.execute(
            """SELECT o.*,t.name type_name,r.*
               FROM occurrences o
               JOIN occurrence_types t ON t.id=o.occurrence_type_id
               LEFT JOIN rma_details r ON r.occurrence_id=o.id
               WHERE o.id=?""",
            (oid,),
        ).fetchone()
        custom = con.execute(
            """SELECT d.*,v.value_text FROM custom_field_defs d
               LEFT JOIN custom_field_values v ON v.field_def_id=d.id AND v.occurrence_id=?
               WHERE d.occurrence_type_id=? AND d.active=1 ORDER BY d.sort_order,d.id""",
            (oid, row["occurrence_type_id"]),
        ).fetchall()
        checklist = con.execute(
            "SELECT * FROM checklist_items WHERE occurrence_id=? ORDER BY id",
            (oid,),
        ).fetchall()
        acts = con.execute(
            "SELECT * FROM activities WHERE occurrence_id=? ORDER BY id DESC LIMIT 150",
            (oid,),
        ).fetchall()
        attachments = con.execute(
            "SELECT * FROM attachments WHERE occurrence_id=? ORDER BY id DESC",
            (oid,),
        ).fetchall()
        refs = con.execute(
            "SELECT * FROM external_refs WHERE occurrence_id=? ORDER BY id DESC",
            (oid,),
        ).fetchall()

    statuses = "".join(f"<option {'selected' if row['status']==x else ''}>{x}</option>" for x in STATUSES)
    priorities = "".join(f"<option {'selected' if row['priority']==x else ''}>{x}</option>" for x in PRIORITIES)
    custom_html = "".join(_custom_control(x) for x in custom)
    workflow_locked = row["type_name"] == "RMA"
    locked_attr = "disabled" if workflow_locked else ""
    if workflow_locked:
        close_action = f"<a class='btn secondary' href='/occurrence/{oid}/close'>Close</a>" if (row["rma_stage"] or "INTAKE") == "COMPLETE" else ""
        detail_actions = f"<button>Save Details</button>{close_action}"
    else:
        detail_actions = f"<button>Save</button><button name='notify_owner' value='1'>Save + Notify Owner</button><a class='btn secondary' href='/occurrence/{oid}/close'>Close</a>"

    common = f"""<div class='panel'><h2>{e(row['case_number'])} | {e(row['type_name'])}</h2><div class='form'>
    <label class='wide'>Title<input name='title' value='{e(row['title'])}'></label>
    <label class='wide'>Description<textarea name='description'>{e(row['description'])}</textarea></label>
    <label>Source<input name='source' value='{e(row['source'])}'></label><label>Customer<input name='customer' value='{e(row['customer'])}'></label>
    <label>Supplier<input name='supplier' value='{e(row['supplier'])}'></label><label>Part<input name='part_number' value='{e(row['part_number'])}'></label>
    <label>Revision<input name='revision' value='{e(row['revision'])}'></label><label>Work order<input name='work_order' value='{e(row['work_order'])}'></label>
    <label>Sales order<input name='sales_order' value='{e(row['sales_order'])}'></label><label>Purchase order<input name='purchase_order' value='{e(row['purchase_order'])}'></label>
    <label>Department<input name='department' value='{e(row['department'])}'></label><label>Work center<input name='work_center' value='{e(row['work_center'])}'></label>
    <label>Owner name<input {locked_attr} name='owner_name' value='{e(row['owner_name'])}'></label><label>Owner email<input {locked_attr} type='email' name='owner_email' value='{e(row['owner_email'])}'></label>
    <label>Priority<select name='priority'>{priorities}</select></label><label>Status<select {locked_attr} name='status'>{statuses}</select></label>
    <label>Due date<input type='date' name='due_date' value='{e(row['due_date'])}'></label>
    <label class='wide'>Next action<input {locked_attr} name='next_action' value='{e(row['next_action'])}'></label>{custom_html}
    </div><div class='toolbar'>{detail_actions}</div></div>"""

    rma = ""
    if row["type_name"] == "RMA":
        recovery_options = "".join(
            f"<option {'selected' if row['recovery_status']==x else ''}>{x}</option>"
            for x in ["NOT REQUIRED", "OPEN", "REQUESTED", "PARTIAL", "RECOVERED", "WAIVED"]
        )
        rma = f"""<br><div class='panel'><h2>RMA</h2><div class='form'>
        <label>RMA Number<input name='rma_number' value='{e(row['rma_number'])}'></label>
        <label>Source Quality No.<input name='quality_no' value='{e(row['quality_no'])}'></label>
        <label>Customer NCR #<input name='customer_ncr' value='{e(row['customer_ncr'])}'></label>
        <label>Total rework cost<input type='number' step='.01' name='total_rework_cost' value='{e(row['total_rework_cost'])}'></label>
        <label>Scrap cost<input type='number' step='.01' name='scrap_cost' value='{e(row['scrap_cost'])}'></label>
        <label>Freight cost<input type='number' step='.01' name='freight_cost' value='{e(row['freight_cost'])}'></label>
        <label>Outside processing cost<input type='number' step='.01' name='outside_processing_cost' value='{e(row['outside_processing_cost'])}'></label>
        <label class='wide'>Discrepancy<textarea name='discrepancy'>{e(row['discrepancy'])}</textarea></label>
        <label><input type='checkbox' name='containment_required' {'checked' if row['containment_required'] else ''}> Containment required</label>
        <label><input type='checkbox' name='containment_complete' {'checked' if row['containment_complete'] else ''}> Containment complete</label>
        <label><input type='checkbox' name='corrective_action_required' {'checked' if row['corrective_action_required'] else ''}> Corrective action required</label>
        <label><input type='checkbox' name='corrective_action_complete' {'checked' if row['corrective_action_complete'] else ''}> Corrective action complete</label>
        <label><input type='checkbox' name='disposition_complete' {'checked' if row['disposition_complete'] else ''}> Disposition complete</label>
        <label>Recovery requested<input type='number' step='.01' name='recovery_requested' value='{e(row['recovery_requested'])}'></label>
        <label>Recovery received<input type='number' step='.01' name='recovery_received' value='{e(row['recovery_received'])}'></label>
        <label>Recovery status<select name='recovery_status'>{recovery_options}</select></label>
        <label>Recovery owner<input name='recovery_owner' value='{e(row['recovery_owner'])}'></label>
        <label>Credit memo #<input name='credit_memo_number' value='{e(row['credit_memo_number'])}'></label>
        <label>Debit memo #<input name='debit_memo_number' value='{e(row['debit_memo_number'])}'></label>
        <label class='wide'>RMA comments<textarea name='sales_comment'>{e(row['sales_comment'])}</textarea></label>
        <label class='wide'>Customer discrepancy<textarea name='customer_discrepancy'>{e(row['customer_discrepancy'])}</textarea></label>
        </div></div>"""

    checklist_html = "".join(
        f"""<label><input type='checkbox' name='item_{x['id']}' value='1' {'checked' if x['completed'] else ''}>
        {e(x['label'])} {'*' if x['required'] else ''}</label>"""
        for x in checklist
    ) or "<span class='muted'>No checklist template is configured for this occurrence type.</span>"

    attachment_html = "".join(
        f"<div><a href='/attachment/{x['id']}'>{e(x['file_name'])}</a> <span class='muted'>{e(x['created_at'])}</span></div>"
        for x in attachments
    ) or "<span class='muted'>No attachments.</span>"

    ref_html = "".join(
        f"<div><b>{e(x['system_name'])}</b> {e(x['entity_type'])}: "
        + (f"<a href='{e(x['external_url'])}' target='_blank'>{e(x['external_id'])}</a>" if x["external_url"] else e(x["external_id"]))
        + f" <span class='muted'>{e(x['note'])}</span></div>"
        for x in refs
    ) or "<span class='muted'>No ERP/external references.</span>"

    activity_html = "".join(
        f"<div class='event'><b>{e(a['activity_type'])}</b> <span class='muted'>{e(a['created_at'])} {e(a['actor'])}</span><div>{e(a['detail'])}</div></div>"
        for a in acts
    ) or "No activity yet."

    source_email = (
        f"<a href='{e(row['source_email_web_link'])}' target='_blank'>Open source email</a>"
        if row["source_email_web_link"]
        else ""
    )

    workflow_ui = ""
    editable = True
    if row["type_name"] == "RMA":
        _actor_name, current_email = _user_identity()
        with connect(db_path()) as con:
            delegates = stage_delegates(con, row["rma_stage"] or "INTAKE")
            allowed = can_advance(con, row["rma_stage"] or "INTAKE", current_email)
        editable = allowed
        workflow_ui = _rma_workflow_ui(row, allowed, delegates)

    if editable:
        details_section = f"<form method='post'>{common}{rma}</form>"
        checklist_section = f"""<div class='panel'><h2>Closure Checklist</h2><form method='post' action='/occurrence/{oid}/checklist' class='form'>
        {checklist_html}<label>Completed by<input name='actor'></label><div class='wide'><button>Update checklist</button></div></form></div>"""
        attachments_section = f"""<div class='panel'><h2>Attachments</h2>{attachment_html}<br><form method='post' action='/occurrence/{oid}/attachment' enctype='multipart/form-data' class='form'>
        <label>File<input type='file' name='attachment' required></label><label>Uploaded by<input name='actor'></label><div><br><button>Attach file</button></div></form></div>"""
        refs_section = f"""<div class='panel'><h2>ERP / External References</h2>{ref_html}<br><form method='post' action='/occurrence/{oid}/external' class='form'>
        <label>System<input name='system_name' placeholder='JobBOSS2'></label><label>Record type<input name='entity_type' placeholder='Job / PO / Sales Order'></label>
        <label>External ID<input name='external_id' required></label><label>URL<input type='url' name='external_url'></label>
        <label class='wide'>Note<input name='note'></label><div><button>Add reference</button></div></form></div>"""
        activity_entry = f"""<div class='panel'><h2>Add Activity</h2><form method='post' action='/occurrence/{oid}/activity' class='form'>
        <label>Type<input name='activity_type' value='NOTE'></label><label>Actor<input name='actor'></label>
        <label class='wide'>Detail<textarea name='detail' required></textarea></label><div><button>Add</button></div></form></div>"""
        email_section = f"""<div class='panel'><h2>Outlook</h2><form method='post' action='/occurrence/{oid}/email' class='form'>
        <label>To<input type='email' name='to' required></label><label>Subject<input name='subject' value='{e(row['case_number'])}: {e(row['title'])}'></label>
        <label class='wide'>Message<textarea name='body' required></textarea></label><div><button>Send</button></div></form></div>"""
    else:
        disabled_common = common.replace("<input ", "<input disabled ").replace("<select ", "<select disabled ").replace("<textarea ", "<textarea disabled ")
        disabled_common = disabled_common.replace(f"<div class='toolbar'>{detail_actions}</div>", "")
        disabled_rma = rma.replace("<input ", "<input disabled ").replace("<select ", "<select disabled ").replace("<textarea ", "<textarea disabled ")
        details_section = disabled_common + disabled_rma
        checklist_section = f"<div class='panel'><h2>Closure Checklist</h2>{checklist_html.replace('<input ', '<input disabled ')}</div>"
        attachments_section = f"<div class='panel'><h2>Attachments</h2>{attachment_html}</div>"
        refs_section = f"<div class='panel'><h2>ERP / External References</h2>{ref_html}</div>"
        activity_entry = ""
        email_section = ""

    body = f"""<h1>{e(row['case_number'])}</h1><div class='toolbar'>{source_email}</div>{workflow_ui}<div class='split'><div>
    {details_section}<br>{checklist_section}<br>{attachments_section}<br>{refs_section}
    {'<br>'+activity_entry if activity_entry else ''}{'<br>'+email_section if email_section else ''}
    </div><div class='panel'><h2>Activity</h2>{activity_html}</div></div>"""
    return page(row["case_number"], body)



@bp.route("/occurrence/<int:oid>/progress", methods=["POST"])
def progress(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(request.referrer or url_for("core.dashboard"))
    detail = request.form.get("detail", "").strip()
    if detail:
        actor_name, actor_email = _user_identity()
        actor = actor_name or actor_email
        with connect(db_path()) as con:
            log_activity(con, oid, "PROGRESS", detail, actor)
    return redirect(request.referrer or url_for("core.dashboard"))


@bp.route("/occurrence/<int:oid>/rma/action", methods=["POST"])
def rma_action(oid):
    actor_name, actor_email = _user_identity()
    if not actor_email:
        flash("Microsoft 365 sign-in is required to complete an RMA action.")
        return redirect(url_for("occurrence.occurrence", oid=oid))

    with connect(db_path()) as con:
        row = con.execute(
            """SELECT o.*,r.* FROM occurrences o JOIN rma_details r ON r.occurrence_id=o.id
               WHERE o.id=?""",
            (oid,),
        ).fetchone()
        if not row:
            return page("Not found", "<div class='panel'>RMA not found.</div>"), 404
        stage = row["rma_stage"] or "INTAKE"
        if not can_advance(con, stage, actor_email):
            flash("This action is read only for the connected user.")
            return redirect(url_for("occurrence.occurrence", oid=oid))

        if stage == "INTAKE":
            con.execute(
                """UPDATE occurrences SET customer=?,purchase_order=?,description=?,updated_at=? WHERE id=?""",
                (
                    request.form.get("customer", "").strip(),
                    request.form.get("purchase_order", "").strip(),
                    request.form.get("notes", "").strip(),
                    utcnow(),
                    oid,
                ),
            )
            con.execute(
                """UPDATE rma_details SET rma_number=?,defect_type=?,csr_name=?,contact_name=?,contact_phone=?,sales_comment=?
                   WHERE occurrence_id=?""",
                (
                    request.form.get("rma_number", "").strip() or None,
                    request.form.get("defect_type", "").strip() or None,
                    request.form.get("csr_name", "").strip() or None,
                    request.form.get("contact_name", "").strip() or None,
                    request.form.get("contact_phone", "").strip() or None,
                    request.form.get("notes", "").strip() or None,
                    oid,
                ),
            )
        elif stage == "AWAITING CUSTOMER RETURN":
            received = request.form.get("received_from_customer", "").strip().upper()
            receive_date = request.form.get("receive_date", "").strip() or (date.today().isoformat() if received == "YES" else None)
            con.execute(
                """UPDATE rma_details SET received_from_customer=?,receive_date=?,hold_area_confirmed=?
                   WHERE occurrence_id=?""",
                (received or None, receive_date, truth(request.form.get("hold_area_confirmed")), oid),
            )
        elif stage == "RMA REVIEW":
            con.execute(
                """UPDATE occurrences SET work_order=?,updated_at=? WHERE id=?""",
                (request.form.get("work_order", "").strip(), utcnow(), oid),
            )
            con.execute(
                """UPDATE rma_details SET product_reviewed=?,work_order_required=?,work_order_issued=?
                   WHERE occurrence_id=?""",
                (
                    truth(request.form.get("product_reviewed")),
                    request.form.get("work_order_required", "").strip().upper() or None,
                    request.form.get("work_order_issued", "").strip().upper() or None,
                    oid,
                ),
            )
        elif stage == "RETURN TO CUSTOMER":
            shipped = truth(request.form.get("shipped_to_customer"))
            shipped_date = request.form.get("returned_to_customer_date", "").strip() or (date.today().isoformat() if shipped else None)
            con.execute(
                """UPDATE rma_details SET final_quality_result=?,approved_to_ship=?,ready_to_ship=?,
                   shipped_to_customer=?,returned_to_customer_date=? WHERE occurrence_id=?""",
                (
                    request.form.get("final_quality_result", "").strip().upper() or None,
                    request.form.get("approved_to_ship", "").strip().upper() or None,
                    request.form.get("ready_to_ship", "").strip().upper() or None,
                    shipped,
                    shipped_date,
                    oid,
                ),
            )

        note = request.form.get("progress_note", "").strip()
        if note:
            log_activity(con, oid, "PROGRESS", note, actor_name or actor_email)

        result = advance_rma(con, oid, actor_name or actor_email)
        if not result.get("ok"):
            for blocker in result.get("blockers", []):
                flash(blocker)
            return redirect(url_for("occurrence.occurrence", oid=oid))

    delivery_errors = 0
    try:
        client = m365()
        primary_emails = set()
        for delegate in result.get("delegates", []):
            email = str(delegate.get("email") or "").strip().lower()
            if not email:
                continue
            primary_emails.add(email)
            try:
                client.send_teams_message(email, result["primary_message"])
            except Exception:
                delivery_errors += 1
        for email in result.get("cc", []):
            email = str(email or "").strip().lower()
            if not email or email in primary_emails:
                continue
            try:
                client.send_teams_message(email, result["cc_message"])
            except Exception:
                delivery_errors += 1
    except Exception:
        delivery_errors += 1

    if delivery_errors:
        flash(f"Stage advanced. {delivery_errors} Teams notification(s) failed.")
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/occurrence/<int:oid>/checklist", methods=["POST"])
def checklist(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
    actor = request.form.get("actor", "")
    with connect(db_path()) as con:
        rows = con.execute("SELECT * FROM checklist_items WHERE occurrence_id=?", (oid,)).fetchall()
        for item in rows:
            completed = 1 if request.form.get(f"item_{item['id']}") else 0
            if completed and not item["completed"]:
                con.execute(
                    "UPDATE checklist_items SET completed=1,completed_at=?,completed_by=? WHERE id=?",
                    (utcnow(), actor, item["id"]),
                )
            elif not completed and item["completed"]:
                con.execute(
                    "UPDATE checklist_items SET completed=0,completed_at=NULL,completed_by=NULL WHERE id=?",
                    (item["id"],),
                )
        log_activity(con, oid, "CHECKLIST", "Closure checklist updated.", actor)
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/occurrence/<int:oid>/attachment", methods=["POST"])
def attachment(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
    upload = request.files.get("attachment")
    if not upload or not upload.filename:
        flash("Choose a file.")
        return redirect(url_for("occurrence.occurrence", oid=oid))
    filename = secure_filename(upload.filename)
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / f"occurrence_{oid}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    upload.save(target)
    with connect(db_path()) as con:
        con.execute(
            "INSERT INTO attachments(occurrence_id,file_name,storage_path,uploaded_by,created_at) VALUES(?,?,?,?,?)",
            (oid, filename, str(target), request.form.get("actor", ""), utcnow()),
        )
        log_activity(con, oid, "ATTACHMENT", f"Attached {filename}.", request.form.get("actor", ""))
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/attachment/<int:attachment_id>")
def attachment_download(attachment_id):
    with connect(db_path()) as con:
        row = con.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
    if not row:
        return page("Not found", "Attachment not found."), 404
    path = Path(row["storage_path"]).resolve()
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    if root not in path.parents or not path.exists():
        return page("Not found", "Attachment file not found."), 404
    return send_file(path, as_attachment=True, download_name=row["file_name"])


@bp.route("/occurrence/<int:oid>/external", methods=["POST"])
def external_reference(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
    external_id = request.form.get("external_id", "").strip()
    if external_id:
        with connect(db_path()) as con:
            con.execute(
                """INSERT OR IGNORE INTO external_refs(
                   occurrence_id,system_name,entity_type,external_id,external_url,note,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    oid,
                    request.form.get("system_name", "").strip() or "External",
                    request.form.get("entity_type", "").strip(),
                    external_id,
                    request.form.get("external_url", "").strip(),
                    request.form.get("note", "").strip(),
                    utcnow(),
                ),
            )
            log_activity(con, oid, "EXTERNAL LINK", f"Linked external record {external_id}.", "")
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/occurrence/<int:oid>/activity", methods=["POST"])
def activity(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
        log_activity(
            con,
            oid,
            request.form.get("activity_type", "NOTE").upper(),
            request.form.get("detail", ""),
            request.form.get("actor", ""),
        )
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/occurrence/<int:oid>/email", methods=["POST"])
def send_email(oid):
    with connect(db_path()) as con:
        if _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
    try:
        m365().send_mail(request.form.get("to", ""), request.form.get("subject", ""), request.form.get("body", ""))
        with connect(db_path()) as con:
            log_activity(
                con,
                oid,
                "OUTLOOK",
                f"Email sent to {request.form.get('to','')}: {request.form.get('subject','')}",
            )
        flash("Outlook email sent.")
    except M365Error as ex:
        flash(f"Outlook send failed: {ex}")
    return redirect(url_for("occurrence.occurrence", oid=oid))


@bp.route("/occurrence/<int:oid>/close", methods=["GET", "POST"])
def close_occurrence(oid):
    with connect(db_path()) as con:
        if request.method == "POST" and _deny_rma_write(con, oid):
            return redirect(url_for("occurrence.occurrence", oid=oid))
        row = con.execute(
            """SELECT o.*,t.name type_name,r.*
               FROM occurrences o JOIN occurrence_types t ON t.id=o.occurrence_type_id
               LEFT JOIN rma_details r ON r.occurrence_id=o.id WHERE o.id=?""",
            (oid,),
        ).fetchone()
        if not row:
            return page("Not found", "Not found"), 404
        ensure_checklist_items(con, oid, row["occurrence_type_id"])
        blockers = generic_close_blockers(con, oid)
        if row["type_name"] == "RMA":
            if (row["rma_stage"] or "INTAKE") != "COMPLETE":
                blockers.append("RMA workflow is not complete.")
            if row["containment_required"] and not row["containment_complete"]:
                blockers.append("Containment is required but incomplete.")
            if row["corrective_action_required"] and not row["corrective_action_complete"]:
                blockers.append("Corrective action is required but incomplete.")
            outstanding = max(fnum(row["recovery_requested"]) - fnum(row["recovery_received"]), 0)
            if outstanding and row["recovery_status"] not in {"RECOVERED", "WAIVED"}:
                blockers.append(f"Recovery outstanding: $" + f"{outstanding:,.2f}.")
        if request.method == "POST" and (not blockers or request.form.get("override")):
            con.execute(
                "UPDATE occurrences SET status='CLOSED',closed_date=?,next_action='',updated_at=? WHERE id=?",
                (date.today().isoformat(), utcnow(), oid),
            )
            log_activity(
                con,
                oid,
                "CLOSE",
                "Occurrence closed." + (" Blockers overridden." if blockers else ""),
                request.form.get("actor", ""),
            )
            return redirect(url_for("core.dashboard"))
    items = "".join(f"<li>{e(x)}</li>" for x in blockers) or "<li>No automated blockers.</li>"
    override = "<label><input type='checkbox' name='override' value='1'> Override blockers</label><br>" if blockers else ""
    return page(
        "Close",
        f"""<h1>Close {e(row['case_number'])}</h1><div class='panel'><ul>{items}</ul>
        <form method='post'><label>Closed by<input name='actor'></label><br>{override}
        <button class='danger'>Close occurrence</button></form></div>""",
    )
