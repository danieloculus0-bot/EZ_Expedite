from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, request, url_for
from werkzeug.utils import secure_filename

from .db import connect, ensure_checklist_items, log_activity, next_case_number, utcnow
from .expediter import run_expeditor
from .generic_import import CORE_FIELDS, auto_mapping, import_generic_file, read_tabular
from .helpers import db_path, e, m365, page
from .importers import import_rma_workbook
from .m365 import M365Error
from .rma_workflow import assign_stage_owner, stage_info

bp = Blueprint("integrations", __name__)


@bp.route("/import/rma", methods=["GET", "POST"])
def rma_import():
    result = ""
    uploads = Path(current_app.config["UPLOAD_FOLDER"])
    if request.method == "POST":
        f = request.files.get("workbook")
        if f and f.filename and f.filename.lower().endswith((".xlsx", ".xlsm")):
            target = uploads / secure_filename(f.filename)
            f.save(target)
            try:
                with connect(db_path()) as con:
                    r = import_rma_workbook(con, target)
                result = f"<div class='notice'>New {r['imported']} | Updated {r['updated']} | Blank skipped {r['skipped']}</div>"
            except Exception as ex:
                result = f"<div class='flash'>{e(ex)}</div>"
    return page(
        "RMA Import",
        f"""<h1>RMA Workbook Import</h1>{result}<div class='panel'>
        <p>Imports the existing NCR/RMA export as RMA occurrences. RMA Number is the canonical synchronization key. Common source aliases such as Quality No. are supported. The workbook remains local and is gitignored.</p>
        <form method='post' enctype='multipart/form-data'><input type='file' name='workbook' accept='.xlsx,.xlsm' required><br><br>
        <button>Import / synchronize</button></form></div>""",
    )


def _header_select(name: str, label: str, headers: list[str], selected: str = "") -> str:
    options = "<option value=''>Do not map</option>" + "".join(
        f"<option value='{e(h)}' {'selected' if h == selected else ''}>{e(h)}</option>" for h in headers
    )
    return f"<label>{e(label)}<select name='{e(name)}'>{options}</select></label>"


@bp.route("/import/generic", methods=["GET", "POST"])
def generic_import():
    uploads = Path(current_app.config["UPLOAD_FOLDER"])
    with connect(db_path()) as con:
        types = con.execute("SELECT * FROM occurrence_types WHERE active=1 ORDER BY name").fetchall()

    if request.method == "GET":
        type_options = "".join(f"<option value='{x['id']}'>{e(x['name'])}</option>" for x in types)
        return page(
            "Import Anything",
            f"""<h1>Import Anything</h1><div class='panel'>
            <p>Bring in an Excel or CSV list from an ERP, spreadsheet, legacy tracker or report. Map its columns into an occurrence type, then synchronize future imports with an external ID column if one exists.</p>
            <form method='post' enctype='multipart/form-data' class='form'>
            <input type='hidden' name='stage' value='preview'>
            <label>Occurrence type<select name='type_id'>{type_options}</select></label>
            <label>Source system / export name<input name='external_system' placeholder='JobBOSS2, Epicor, Supplier Log...'></label>
            <label class='wide'>Excel or CSV<input type='file' name='workbook' accept='.xlsx,.xlsm,.csv' required></label>
            <div><button>Read columns</button></div></form></div>""",
        )

    stage = request.form.get("stage", "preview")
    if stage == "preview":
        f = request.files.get("workbook")
        if not f or not f.filename:
            flash("Choose an Excel or CSV file.")
            return redirect(url_for("integrations.generic_import"))
        filename = secure_filename(f.filename)
        target = uploads / filename
        f.save(target)
        type_id = int(request.form["type_id"])
        external_system = request.form.get("external_system", "").strip()
        headers, _ = read_tabular(target)
        mapping = auto_mapping(headers)
        with connect(db_path()) as con:
            t = con.execute("SELECT * FROM occurrence_types WHERE id=?", (type_id,)).fetchone()
            custom = con.execute(
                "SELECT * FROM custom_field_defs WHERE occurrence_type_id=? AND active=1 ORDER BY sort_order,id",
                (type_id,),
            ).fetchall()
        if not t:
            flash("Occurrence type not found.")
            return redirect(url_for("integrations.generic_import"))

        labels = {
            "title": "Title / Subject",
            "description": "Description / Details",
            "source": "Source",
            "customer": "Customer",
            "supplier": "Supplier",
            "part_number": "Part Number",
            "revision": "Revision",
            "work_order": "Work Order / Job",
            "sales_order": "Sales Order",
            "purchase_order": "Purchase Order",
            "department": "Department",
            "work_center": "Work Center",
            "owner_name": "Owner Name",
            "owner_email": "Owner Email",
            "priority": "Priority",
            "status": "Status",
            "next_action": "Next Action",
            "due_date": "Due Date",
            "created_date": "Created / Opened Date",
        }
        selects = "".join(
            _header_select(f"map_{field}", labels[field], headers, mapping.get(field, "")) for field in CORE_FIELDS
        )
        custom_selects = "".join(
            _header_select(f"map_custom_{field['id']}", f"Custom: {field['label']}", headers, "") for field in custom
        )
        id_options = "<option value=''>No synchronization key</option>" + "".join(
            f"<option value='{e(h)}'>{e(h)}</option>" for h in headers
        )
        return page(
            "Map Import",
            f"""<h1>Map {e(t['name'])} Import</h1><div class='notice'>File: {e(filename)} | {len(headers)} columns detected</div>
            <form method='post' class='panel form'>
            <input type='hidden' name='stage' value='import'><input type='hidden' name='filename' value='{e(filename)}'>
            <input type='hidden' name='type_id' value='{type_id}'><input type='hidden' name='external_system' value='{e(external_system)}'>
            <label>External ID / synchronization key<select name='external_id_column'>{id_options}</select></label>
            {selects}{custom_selects}
            <div class='wide'><button>Import / synchronize occurrences</button></div></form>""",
        )

    filename = secure_filename(request.form.get("filename", ""))
    target = uploads / filename
    if not filename or not target.exists():
        flash("The uploaded import file is no longer available.")
        return redirect(url_for("integrations.generic_import"))
    type_id = int(request.form["type_id"])
    mapping = {field: request.form.get(f"map_{field}", "") for field in CORE_FIELDS}
    with connect(db_path()) as con:
        custom = con.execute(
            "SELECT id FROM custom_field_defs WHERE occurrence_type_id=? AND active=1",
            (type_id,),
        ).fetchall()
        for field in custom:
            mapping[f"custom:{field['id']}"] = request.form.get(f"map_custom_{field['id']}", "")
        result = import_generic_file(
            con,
            target,
            type_id,
            mapping,
            external_system=request.form.get("external_system", "").strip(),
            external_id_column=request.form.get("external_id_column", ""),
        )
    flash(f"Import complete. Created {result['created']}; updated {result['updated']}.")
    return redirect(url_for("core.dashboard"))


@bp.route("/systems", methods=["GET", "POST"])
def systems():
    with connect(db_path()) as con:
        if request.method == "POST":
            now = utcnow()
            name = request.form.get("name", "").strip()
            if name:
                con.execute(
                    """INSERT INTO external_connections(name,provider,mode,base_url,enabled,notes,created_at,updated_at)
                       VALUES(?,?,?,?,1,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET provider=excluded.provider,mode=excluded.mode,
                       base_url=excluded.base_url,notes=excluded.notes,updated_at=excluded.updated_at""",
                    (
                        name,
                        request.form.get("provider", "Other"),
                        request.form.get("mode", "flat_file"),
                        request.form.get("base_url", "").strip(),
                        request.form.get("notes", "").strip(),
                        now,
                        now,
                    ),
                )
            return redirect(url_for("integrations.systems"))
        rows = con.execute("SELECT * FROM external_connections ORDER BY name").fetchall()
    tr = "".join(
        f"<tr><td>{e(x['name'])}</td><td>{e(x['provider'])}</td><td>{e(x['mode'])}</td><td>{e(x['base_url'])}</td><td>{e(x['notes'])}</td></tr>"
        for x in rows
    )
    return page(
        "ERP / Systems",
        f"""<h1>ERP / External Systems</h1>
        <div class='notice'>EZ Expedite can work immediately from flat-file/Excel/CSV exports. Direct API connections are configured only with real vendor endpoint and authentication information. No guessed ERP endpoints are built into the app.</div>
        <div class='panel'><form method='post' class='form'>
        <label>Connection name<input name='name' placeholder='EZ Fab JobBOSS2'></label>
        <label>Provider<select name='provider'><option>JobBOSS2</option><option>Epicor</option><option>Plex</option><option>SAP</option><option>Other</option></select></label>
        <label>Mode<select name='mode'><option value='flat_file'>Excel / CSV flat file</option><option value='public_api'>Public API</option><option value='custom_rest'>Custom REST API</option><option value='database_view'>Read-only database/report view</option></select></label>
        <label>Base URL / endpoint root<input name='base_url' placeholder='Only when supplied by ERP vendor/admin'></label>
        <label class='wide'>Notes<textarea name='notes' placeholder='What records this connection should provide, auth owner, report name, etc.'></textarea></label>
        <div><button>Save connection</button></div></form></div><br>
        <div class='panel'><table><tr><th>Name</th><th>Provider</th><th>Mode</th><th>Base URL</th><th>Notes</th></tr>
        {tr or '<tr><td colspan=5>No external systems configured.</td></tr>'}</table></div>""",
    )


@bp.route("/expedite/run")
def expedite_now():
    client = None
    try:
        client = m365()
        client.me()
    except Exception:
        client = None
    with connect(db_path()) as con:
        result = run_expeditor(
            con,
            notify_teams=(lambda recipient, message: client.send_teams_message(recipient, message)) if client else None,
        )
    if client:
        flash(
            f"Checked {result['checked']} open occurrences. Past-due items: {result['overdue_items']}. "
            f"Daily digests sent: {result['digests_sent']}. Unassigned: {result['unassigned']}. "
            f"Due without next action: {result['due_without_action']}. Errors: {result['errors']}."
        )
    else:
        flash(
            f"Checked {result['checked']} open occurrences. Past-due items: {result['overdue_items']}. "
            f"Microsoft 365 is not connected. Unassigned: {result['unassigned']}. "
            f"Due without next action: {result['due_without_action']}."
        )
    return redirect(url_for("core.dashboard"))


@bp.route("/mail/inbox")
def mail_inbox():
    try:
        msgs = m365().recent_inbox(25)
    except M365Error as ex:
        return page(
            "Outlook",
            f"<h1>Outlook Inbox</h1><div class='flash'>{e(ex)}</div><a class='btn' href='/setup'>Setup Microsoft 365</a>",
        )
    with connect(db_path()) as con:
        linked = {x["message_id"]: x["occurrence_id"] for x in con.execute("SELECT message_id,occurrence_id FROM occurrence_emails")}
        types = con.execute("SELECT * FROM occurrence_types WHERE active=1 ORDER BY CASE WHEN name='RMA' THEN 0 ELSE 1 END,name").fetchall()
    type_options = "".join(f"<option value='{x['id']}'>{e(x['name'])}</option>" for x in types)
    tr = ""
    for m in msgs:
        sender = ((m.get("from") or {}).get("emailAddress") or {})
        mid = m.get("id", "")
        if mid in linked:
            action = f"<a href='/occurrence/{linked[mid]}'>Open linked case</a>"
        else:
            action = f"""<form method='post' action='/mail/create'>
            <input type='hidden' name='message_id' value='{e(mid)}'><select name='type_id'>{type_options}</select><br><br>
            <button>Create occurrence</button></form>"""
        tr += f"<tr><td>{e(m.get('receivedDateTime'))}</td><td>{e(sender.get('address'))}</td><td><b>{e(m.get('subject'))}</b><br><span class='muted'>{e(m.get('bodyPreview'))}</span></td><td>{action}</td></tr>"
    return page(
        "Outlook",
        f"<h1>Outlook Inbox</h1><div class='panel table'><table><tr><th>Received</th><th>From</th><th>Message</th><th>Action</th></tr>{tr}</table></div>",
    )


@bp.route("/mail/create", methods=["POST"])
def mail_create():
    mid = request.form.get("message_id", "")
    try:
        m = m365().message(mid)
    except M365Error as ex:
        flash(str(ex))
        return redirect(url_for("integrations.mail_inbox"))
    sender = ((m.get("from") or {}).get("emailAddress") or {})
    with connect(db_path()) as con:
        old = con.execute("SELECT occurrence_id FROM occurrence_emails WHERE message_id=?", (mid,)).fetchone()
        if old:
            return redirect(url_for("occurrence.occurrence", oid=old[0]))
        type_id = int(request.form.get("type_id") or 0)
        type_row = con.execute("SELECT * FROM occurrence_types WHERE id=? AND active=1", (type_id,)).fetchone()
        if not type_row:
            flash("Occurrence type not found.")
            return redirect(url_for("integrations.mail_inbox"))
        num = next_case_number(con, type_id)
        now = utcnow()
        cur = con.execute(
            """INSERT INTO occurrences(
               case_number,occurrence_type_id,title,description,source,customer,priority,status,next_action,
               created_date,last_activity_at,source_email_id,source_email_web_link,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                num,
                type_id,
                m.get("subject") or "Outlook occurrence",
                m.get("bodyPreview") or "",
                "Outlook: " + sender.get("address", ""),
                sender.get("name") or sender.get("address", ""),
                "Normal",
                "NEW",
                "Review source email and assign owner",
                date.today().isoformat(),
                now,
                mid,
                m.get("webLink", ""),
                now,
                now,
            ),
        )
        oid = int(cur.lastrowid)
        if type_row["name"] == "RMA":
            con.execute("INSERT INTO rma_details(occurrence_id,recovery_status) VALUES(?,?)", (oid, "NOT REQUIRED"))
            assign_stage_owner(con, oid, "INTAKE")
            con.execute(
                "UPDATE occurrences SET next_action=?,updated_at=? WHERE id=?",
                (stage_info("INTAKE").action, utcnow(), oid),
            )
        ensure_checklist_items(con, oid, type_id)
        con.execute(
            """INSERT INTO occurrence_emails(
               occurrence_id,message_id,subject,sender_name,sender_email,received_at,web_link,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                oid,
                mid,
                m.get("subject", ""),
                sender.get("name", ""),
                sender.get("address", ""),
                m.get("receivedDateTime", ""),
                m.get("webLink", ""),
                now,
            ),
        )
        log_activity(con, oid, "OUTLOOK", "Occurrence created from Outlook email.", sender.get("address", ""))
    return redirect(url_for("occurrence.occurrence", oid=oid))
