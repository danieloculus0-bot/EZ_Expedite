from __future__ import annotations

from datetime import date, datetime, timedelta
import os

from flask import Blueprint, flash, redirect, request, url_for

from .db import (
    connect,
    ensure_checklist_items,
    get_setting,
    log_activity,
    next_case_number,
    set_setting,
    utcnow,
)
from .helpers import PRIORITIES, STATUSES, db_path, e, m365, page, profile
from .m365 import M365Error

bp = Blueprint("core", __name__)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    with connect(db_path()) as con:
        if request.method == "POST":
            set_setting(con, "m365_client_id", request.form.get("client_id", "").strip())
            set_setting(con, "m365_tenant", request.form.get("tenant", "organizations").strip() or "organizations")
            interval = request.form.get("expediter_interval_minutes", "30").strip()
            try:
                interval = str(max(5, int(interval)))
            except ValueError:
                interval = "30"
            set_setting(con, "expediter_interval_minutes", interval)
            if request.form.get("finish"):
                set_setting(con, "setup_complete", "1")
            flash("Setup saved.")
            if request.form.get("connect"):
                return redirect(url_for("core.m365_connect"))
        cid = os.environ.get("M365_CLIENT_ID") or get_setting(con, "m365_client_id")
        tenant = os.environ.get("M365_TENANT") or get_setting(con, "m365_tenant", "organizations")
        expedite_interval = get_setting(con, "expediter_interval_minutes", "30")
    p = profile()
    state = f"Connected: {e(p.get('displayName') or p.get('userPrincipalName'))}" if p else "Outlook and Teams are not connected."
    body = f"""
    <h1>Microsoft 365 Setup</h1>
    <div class='panel'>
      <div class='notice'>{state}</div>
      <p>One Microsoft sign-in connects Outlook and Teams. EZ Expedite never asks for or stores the user's Microsoft password.</p>
      <form method='post' class='form'>
        <label>Application Client ID<input name='client_id' value='{e(cid)}' placeholder='One-time app identifier'></label>
        <label>Tenant<input name='tenant' value='{e(tenant)}'></label>
        <label>Expediter check interval (minutes)<input type='number' min='5' name='expediter_interval_minutes' value='{e(expedite_interval)}'></label>
        <div><br><button name='connect' value='1'>Save + Connect Microsoft 365</button></div>
        <div class='wide'><button class='secondary' name='finish' value='1'>Finish setup</button></div>
      </form>
      <p class='muted'>Delegated permissions: User.Read, User.ReadBasic.All, Mail.Read, Mail.Send, Chat.Create, ChatMessage.Send. The Client ID is not a password or client secret.</p>
    </div>
    """
    return page("Setup", body)


@bp.route("/m365/connect")
def m365_connect():
    try:
        m365().connect_interactive()
        flash("Microsoft 365 connected.")
    except M365Error as ex:
        flash(str(ex))
    return redirect(url_for("core.setup"))


@bp.route("/")
def dashboard():
    today = date.today().isoformat()
    stale = (datetime.utcnow() - timedelta(days=7)).replace(microsecond=0).isoformat() + "Z"
    q = request.args.get("q", "").strip()
    type_filter = request.args.get("type", "").strip()
    status_filter = request.args.get("status", "").strip()

    with connect(db_path()) as con:
        metrics = {
            "Open": con.execute("SELECT COUNT(*) FROM occurrences WHERE status!='CLOSED'").fetchone()[0],
            "Overdue": con.execute(
                "SELECT COUNT(*) FROM occurrences WHERE status!='CLOSED' AND due_date IS NOT NULL AND due_date<?",
                (today,),
            ).fetchone()[0],
            "Unassigned": con.execute(
                "SELECT COUNT(*) FROM occurrences WHERE status!='CLOSED' AND COALESCE(owner_email,'')='' AND COALESCE(owner_name,'')=''"
            ).fetchone()[0],
            "Stale 7+ days": con.execute(
                "SELECT COUNT(*) FROM occurrences WHERE status!='CLOSED' AND COALESCE(last_activity_at,created_at)<?",
                (stale,),
            ).fetchone()[0],
            "Awaiting Recovery": con.execute(
                """SELECT COUNT(*) FROM occurrences o JOIN rma_details r ON r.occurrence_id=o.id
                   WHERE o.status!='CLOSED' AND r.recovery_status IN ('OPEN','REQUESTED','PARTIAL')"""
            ).fetchone()[0],
        }
        money = con.execute(
            "SELECT COALESCE(SUM(recovery_requested),0)-COALESCE(SUM(recovery_received),0) FROM rma_details"
        ).fetchone()[0]
        sql = """SELECT o.*,t.name type_name,r.rma_number,r.quality_no
                 FROM occurrences o
                 JOIN occurrence_types t ON t.id=o.occurrence_type_id
                 LEFT JOIN rma_details r ON r.occurrence_id=o.id
                 WHERE o.status!='CLOSED'"""
        params: list[str] = []
        if q:
            sql += """ AND (o.case_number LIKE ? OR o.title LIKE ? OR o.description LIKE ? OR o.customer LIKE ?
                       OR o.supplier LIKE ? OR o.part_number LIKE ? OR o.work_order LIKE ? OR o.owner_name LIKE ?
                       OR r.rma_number LIKE ? OR r.quality_no LIKE ?)"""
            needle = f"%{q}%"
            params.extend([needle] * 10)
        if type_filter:
            sql += " AND t.name=?"
            params.append(type_filter)
        if status_filter:
            sql += " AND o.status=?"
            params.append(status_filter)
        sql += """ ORDER BY CASE o.priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 ELSE 2 END,
                   CASE WHEN o.due_date IS NULL THEN 1 ELSE 0 END,o.due_date,o.id DESC LIMIT 500"""
        rows = con.execute(sql, params).fetchall()
        types = con.execute("SELECT name FROM occurrence_types WHERE active=1 ORDER BY name").fetchall()

    cards = "".join(
        f"<div class='card metric'><span>{e(k)}</span><b>{v}</b></div>" for k, v in metrics.items()
    ) + f"<div class='card metric'><span>Recovery Outstanding</span><b>$" + f"{max(float(money or 0),0):,.0f}</b></div>"

    tr = "".join(
        f"""<tr>
        <td><a href='/occurrence/{r['id']}'>{e(r['case_number'])}</a><br><span class='muted'>{e(r['rma_number'])}</span></td>
        <td>{e(r['type_name'])}</td><td>{e(r['title'])}</td><td>{e(r['owner_name'] or r['owner_email'])}</td>
        <td><span class='status'>{e(r['status'])}</span></td>
        <td class='{"bad" if r['due_date'] and r['due_date'] < today else ""}'>{e(r['due_date'])}</td><td>{e(r['next_action'])}</td>
        </tr>"""
        for r in rows
    )
    type_options = "<option value=''>All types</option>" + "".join(
        f"<option {'selected' if type_filter==x['name'] else ''}>{e(x['name'])}</option>" for x in types
    )
    status_options = "<option value=''>All open statuses</option>" + "".join(
        f"<option {'selected' if status_filter==x else ''}>{e(x)}</option>" for x in STATUSES if x != "CLOSED"
    )
    filters = f"""<form method='get' class='form panel'>
      <label>Search<input name='q' value='{e(q)}' placeholder='case, RMA number, customer, part, owner, description...'></label>
      <label>Type<select name='type'>{type_options}</select></label>
      <label>Status<select name='status'>{status_options}</select></label>
      <div><br><button>Filter</button> <a class='btn secondary' href='/'>Clear</a></div>
    </form>"""
    return page(
        "Dashboard",
        f"""<h1>Expedite Dashboard</h1><div class='grid'>{cards}</div>
        <div class='toolbar'><a class='btn' href='/occurrence/new'>New occurrence</a>
        <a class='btn secondary' href='/expedite/run'>Run Expediter</a>
        <a class='btn secondary' href='/mail/inbox'>Review Outlook inbox</a></div>
        {filters}<br><div class='panel table'><table><tr><th>Case</th><th>Type</th><th>Occurrence</th>
        <th>Owner</th><th>Status</th><th>Due</th><th>Next action</th></tr>
        {tr or '<tr><td colspan=7>No matching open occurrences.</td></tr>'}</table></div>""",
    )


@bp.route("/types", methods=["GET", "POST"])
def types():
    with connect(db_path()) as con:
        if request.method == "POST":
            name = request.form.get("name", "").strip().upper()
            prefix = request.form.get("prefix", "EXP").strip().upper()[:12] or "EXP"
            if name:
                con.execute(
                    "INSERT OR IGNORE INTO occurrence_types(name,prefix,active,created_at) VALUES(?,?,1,?)",
                    (name, prefix, utcnow()),
                )
            return redirect(url_for("core.types"))
        rows = con.execute(
            """SELECT t.*,
               (SELECT COUNT(*) FROM custom_field_defs f WHERE f.occurrence_type_id=t.id AND f.active=1) field_count,
               (SELECT COUNT(*) FROM checklist_templates c WHERE c.occurrence_type_id=t.id AND c.active=1) checklist_count
               FROM occurrence_types t ORDER BY name"""
        ).fetchall()
    tr = "".join(
        f"<tr><td><a href='/type/{r['id']}'>{e(r['name'])}</a></td><td>{e(r['prefix'])}</td><td>{r['field_count']}</td><td>{r['checklist_count']}</td></tr>"
        for r in rows
    )
    return page(
        "Types",
        f"""<h1>Occurrence Types</h1><div class='panel'><p>RMA starts the system. Add any process that needs ownership, action, due dates, escalation and closure.</p>
        <form method='post' class='form'><label>Type<input name='name' placeholder='SUPPLIER ISSUE'></label>
        <label>Prefix<input name='prefix' placeholder='SUP'></label><div><br><button>Add type</button></div></form></div><br>
        <div class='panel'><table><tr><th>Type</th><th>Prefix</th><th>Custom fields</th><th>Checklist items</th></tr>{tr}</table></div>""",
    )


@bp.route("/type/<int:type_id>", methods=["GET", "POST"])
def type_config(type_id):
    with connect(db_path()) as con:
        t = con.execute("SELECT * FROM occurrence_types WHERE id=?", (type_id,)).fetchone()
        if not t:
            return page("Not found", "<div class='panel'>Occurrence type not found.</div>"), 404
        if request.method == "POST":
            action = request.form.get("_action")
            if action == "field":
                name = request.form.get("name", "").strip().lower().replace(" ", "_")
                label = request.form.get("label", "").strip()
                field_type = request.form.get("field_type", "text")
                if name and label:
                    con.execute(
                        """INSERT OR IGNORE INTO custom_field_defs(
                           occurrence_type_id,name,label,field_type,required,options_text,sort_order,active)
                           VALUES(?,?,?,?,?,?,?,1)""",
                        (
                            type_id,
                            name,
                            label,
                            field_type,
                            1 if request.form.get("required") else 0,
                            request.form.get("options_text", "").strip(),
                            int(request.form.get("sort_order") or 100),
                        ),
                    )
            elif action == "checklist":
                label = request.form.get("label", "").strip()
                if label:
                    con.execute(
                        """INSERT INTO checklist_templates(occurrence_type_id,label,required,sort_order,active)
                           VALUES(?,?,?,?,1)""",
                        (
                            type_id,
                            label,
                            1 if request.form.get("required") else 0,
                            int(request.form.get("sort_order") or 100),
                        ),
                    )
            return redirect(url_for("core.type_config", type_id=type_id))
        fields = con.execute(
            "SELECT * FROM custom_field_defs WHERE occurrence_type_id=? AND active=1 ORDER BY sort_order,id",
            (type_id,),
        ).fetchall()
        checklist = con.execute(
            "SELECT * FROM checklist_templates WHERE occurrence_type_id=? AND active=1 ORDER BY sort_order,id",
            (type_id,),
        ).fetchall()
    field_rows = "".join(
        f"<tr><td>{e(x['label'])}</td><td>{e(x['name'])}</td><td>{e(x['field_type'])}</td><td>{'Yes' if x['required'] else 'No'}</td><td>{e(x['options_text'])}</td></tr>"
        for x in fields
    )
    check_rows = "".join(
        f"<tr><td>{e(x['label'])}</td><td>{'Yes' if x['required'] else 'No'}</td></tr>" for x in checklist
    )
    return page(
        t["name"],
        f"""<h1>{e(t['name'])} Configuration</h1>
        <div class='panel'><h2>Custom fields</h2><form method='post' class='form'>
        <input type='hidden' name='_action' value='field'>
        <label>Internal name<input name='name' placeholder='serial_number'></label>
        <label>Display label<input name='label' placeholder='Serial Number'></label>
        <label>Field type<select name='field_type'><option>text</option><option>textarea</option><option>number</option><option>date</option><option>email</option><option>url</option><option>checkbox</option><option>select</option></select></label>
        <label>Select options<input name='options_text' placeholder='Open|Waiting|Done'></label>
        <label>Sort order<input type='number' name='sort_order' value='100'></label>
        <label><input type='checkbox' name='required'> Required before closure</label><div><br><button>Add field</button></div>
        </form><br><table><tr><th>Label</th><th>Name</th><th>Type</th><th>Required</th><th>Options</th></tr>{field_rows or '<tr><td colspan=5>No custom fields.</td></tr>'}</table></div>
        <br><div class='panel'><h2>Closure checklist</h2><form method='post' class='form'>
        <input type='hidden' name='_action' value='checklist'><label>Checklist item<input name='label' placeholder='Customer notified'></label>
        <label>Sort order<input type='number' name='sort_order' value='100'></label>
        <label><input type='checkbox' name='required' checked> Required before closure</label><div><br><button>Add checklist item</button></div>
        </form><br><table><tr><th>Item</th><th>Required</th></tr>{check_rows or '<tr><td colspan=2>No checklist templates.</td></tr>'}</table></div>""",
    )


@bp.route("/occurrence/new", methods=["GET", "POST"])
def new_occurrence():
    with connect(db_path()) as con:
        types = con.execute(
            "SELECT * FROM occurrence_types WHERE active=1 ORDER BY CASE WHEN name='RMA' THEN 0 ELSE 1 END,name"
        ).fetchall()
        if request.method == "POST":
            tid = int(request.form["type_id"])
            num = next_case_number(con, tid)
            now = utcnow()
            cur = con.execute(
                """INSERT INTO occurrences(
                   case_number,occurrence_type_id,title,description,source,customer,supplier,part_number,revision,
                   work_order,sales_order,purchase_order,department,work_center,owner_name,owner_email,priority,status,
                   next_action,due_date,created_date,last_activity_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    num,
                    tid,
                    request.form.get("title") or "Untitled occurrence",
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
                    request.form.get("owner_name", ""),
                    request.form.get("owner_email", ""),
                    request.form.get("priority", "Normal"),
                    request.form.get("status", "NEW"),
                    request.form.get("next_action", ""),
                    request.form.get("due_date") or None,
                    date.today().isoformat(),
                    now,
                    now,
                    now,
                ),
            )
            oid = int(cur.lastrowid)
            tname = con.execute("SELECT name FROM occurrence_types WHERE id=?", (tid,)).fetchone()[0]
            if tname == "RMA":
                con.execute(
                    "INSERT INTO rma_details(occurrence_id,recovery_status) VALUES(?,?)",
                    (oid, "NOT REQUIRED"),
                )
            ensure_checklist_items(con, oid, tid)
            log_activity(con, oid, "CREATE", f"{tname} occurrence created.", request.form.get("owner_name", ""))
            return redirect(url_for("occurrence.occurrence", oid=oid))
    opts = "".join(f"<option value='{x['id']}'>{e(x['name'])}</option>" for x in types)
    priorities = "".join(f"<option>{x}</option>" for x in PRIORITIES)
    statuses = "".join(f"<option>{x}</option>" for x in STATUSES[:-1])
    body = f"""<h1>New Occurrence</h1><form method='post' class='panel form'>
    <label>Type<select name='type_id'>{opts}</select></label><label>Priority<select name='priority'>{priorities}</select></label>
    <label>Status<select name='status'>{statuses}</select></label>
    <label class='wide'>Title<input name='title' required value='{e(request.args.get("title"))}'></label>
    <label class='wide'>Description<textarea name='description'>{e(request.args.get("description"))}</textarea></label>
    <label>Source<input name='source' value='{e(request.args.get("source"))}'></label>
    <label>Customer<input name='customer'></label><label>Supplier<input name='supplier'></label>
    <label>Part<input name='part_number'></label><label>Revision<input name='revision'></label>
    <label>Work order<input name='work_order'></label><label>Sales order<input name='sales_order'></label>
    <label>Purchase order<input name='purchase_order'></label><label>Department<input name='department'></label>
    <label>Work center<input name='work_center'></label><label>Owner name<input name='owner_name'></label>
    <label>Owner email<input name='owner_email' type='email'></label><label>Due date<input name='due_date' type='date'></label>
    <label class='wide'>Next action<input name='next_action'></label><div><button>Create occurrence</button></div></form>"""
    return page("New", body)
