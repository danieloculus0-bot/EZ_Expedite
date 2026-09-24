from __future__ import annotations

from datetime import date, datetime, timedelta
import os

from flask import Blueprint, flash, redirect, request, url_for

from .auth import AuthConfigError, begin_sign_in, complete_sign_in, sign_out
from .db import (
    connect,
    ensure_checklist_items,
    get_setting,
    log_activity,
    next_case_number,
    set_setting,
    utcnow,
)
from .helpers import PRIORITIES, STATUSES, db_path, e, m365, page, profile, safe_hex
from .m365 import M365Error
from .rma_workflow import assign_stage_owner, stage_info

bp = Blueprint("core", __name__)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    with connect(db_path()) as con:
        if request.method == "POST":
            set_setting(con, "m365_client_id", request.form.get("client_id", "").strip())
            set_setting(con, "m365_tenant", request.form.get("tenant", "organizations").strip() or "organizations")
            set_setting(con, "m365_client_secret", request.form.get("client_secret", "").strip())
            set_setting(con, "public_base_url", request.form.get("public_base_url", "").strip())
            set_setting(con, "multi_user_mode", "1" if request.form.get("multi_user_mode") else "0")
            network_mode = request.form.get("network_mode", "local")
            set_setting(con, "listen_host", "0.0.0.0" if network_mode == "shared" else "127.0.0.1")
            set_setting(con, "listen_port", request.form.get("listen_port", "5050").strip() or "5050")
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
        client_secret = os.environ.get("M365_CLIENT_SECRET") or get_setting(con, "m365_client_secret", "")
        public_base_url = os.environ.get("EZ_EXPEDITE_PUBLIC_BASE_URL") or get_setting(con, "public_base_url", "")
        multi_user_mode = get_setting(con, "multi_user_mode", "1") == "1"
        listen_host = get_setting(con, "listen_host", "127.0.0.1")
        listen_port = get_setting(con, "listen_port", "5050")
        network_mode = "shared" if listen_host == "0.0.0.0" else "local"
        expedite_interval = get_setting(con, "expediter_interval_minutes", "30")
    try:
        notification_profile = m365().me()
    except Exception:
        notification_profile = None
    state = (
        f"Notification account: {e(notification_profile.get('displayName') or notification_profile.get('userPrincipalName'))}"
        if notification_profile
        else "Notification account not connected."
    )
    body = f"""
    <h1>Microsoft 365 Setup</h1>
    <div class='panel'>
      <div class='notice'>{state}</div>
      <p>One Microsoft sign-in connects Outlook and Teams. EZ Expedite never asks for or stores the user's Microsoft password.</p>
      <form method='post' class='form'>
        <label>Application Client ID<input name='client_id' value='{e(cid)}' placeholder='One-time app identifier'></label>
        <label>Tenant<input name='tenant' value='{e(tenant)}'></label>
        <label>Web sign-in secret<input type='password' name='client_secret' value='{e(client_secret)}'></label>
        <label>Public base URL<input name='public_base_url' value='{e(public_base_url)}' placeholder='https://server.example.com'></label>
        <label>Network access<select name='network_mode'>
          <option value='local' {'selected' if network_mode == 'local' else ''}>Local only</option>
          <option value='shared' {'selected' if network_mode == 'shared' else ''}>Shared network</option>
        </select></label>
        <label>Port<input type='number' min='1024' max='65535' name='listen_port' value='{e(listen_port)}'></label>
        <label>Expediter check interval (minutes)<input type='number' min='5' name='expediter_interval_minutes' value='{e(expedite_interval)}'></label>
        <label><input type='checkbox' name='multi_user_mode' value='1' {'checked' if multi_user_mode else ''}> Multi-user delegate sign-in</label>
        <div><br><button name='connect' value='1'>Save + Connect notification account</button></div>
        <div class='wide'><button class='secondary' name='finish' value='1'>Finish setup</button></div>
      </form>
      <p class='muted'>Notification account permissions: User.Read, User.ReadBasic.All, Mail.Read, Mail.Send, Chat.Create, ChatMessage.Send.</p>
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


@bp.route("/auth/login")
def auth_login():
    try:
        return redirect(begin_sign_in())
    except AuthConfigError as ex:
        flash(str(ex))
        return redirect(url_for("core.setup"))


@bp.route("/auth/callback")
def auth_callback():
    try:
        complete_sign_in(request.args.to_dict(flat=True))
        return redirect(url_for("core.dashboard"))
    except AuthConfigError as ex:
        flash(str(ex))
        return redirect(url_for("core.setup"))


@bp.route("/auth/logout")
def auth_logout():
    sign_out()
    return redirect(url_for("core.dashboard"))


@bp.route("/")
def dashboard():
    today_obj = date.today()
    today = today_obj.isoformat()
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

        overdue_rows = con.execute(
            """SELECT due_date FROM occurrences
               WHERE status!='CLOSED' AND due_date IS NOT NULL AND due_date<?""",
            (today,),
        ).fetchall()
        aging = {"1-3 days": 0, "4-7 days": 0, "8-14 days": 0, "15-30 days": 0, "31+ days": 0}
        for item in overdue_rows:
            try:
                days = (today_obj - datetime.strptime(item["due_date"], "%Y-%m-%d").date()).days
            except (TypeError, ValueError):
                continue
            if days <= 3:
                aging["1-3 days"] += 1
            elif days <= 7:
                aging["4-7 days"] += 1
            elif days <= 14:
                aging["8-14 days"] += 1
            elif days <= 30:
                aging["15-30 days"] += 1
            else:
                aging["31+ days"] += 1

        sql = """SELECT o.*,t.name type_name,r.rma_number,r.quality_no,
                 (SELECT a.detail FROM activities a
                    WHERE a.occurrence_id=o.id AND a.activity_type IN ('PROGRESS','NOTE')
                    ORDER BY a.id DESC LIMIT 1) last_note,
                 (SELECT a.created_at FROM activities a
                    WHERE a.occurrence_id=o.id AND a.activity_type IN ('PROGRESS','NOTE')
                    ORDER BY a.id DESC LIMIT 1) last_note_at
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
        sql += """ ORDER BY CASE WHEN o.due_date IS NOT NULL AND o.due_date<? THEN 0 ELSE 1 END,
                   CASE o.priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 ELSE 2 END,
                   CASE WHEN o.due_date IS NULL THEN 1 ELSE 0 END,o.due_date,o.id DESC LIMIT 500"""
        params.append(today)
        rows = con.execute(sql, params).fetchall()
        types = con.execute("SELECT name FROM occurrence_types WHERE active=1 ORDER BY name").fetchall()

    cards = "".join(
        f"<div class='card metric'><span>{e(k)}</span><b>{v}</b></div>" for k, v in metrics.items()
    ) + f"<div class='card metric'><span>Recovery Outstanding</span><b>$" + f"{max(float(money or 0),0):,.0f}</b></div>"

    heat = "".join(
        f"<div class='aging-cell heat-{i}'><span>{e(label)}</span><b>{count}</b></div>"
        for i, (label, count) in enumerate(aging.items(), start=1)
    )

    table_rows = []
    for row in rows:
        overdue = 0
        if row["due_date"]:
            try:
                overdue = max((today_obj - datetime.strptime(row["due_date"], "%Y-%m-%d").date()).days, 0)
            except ValueError:
                overdue = 0
        age_text = f"{overdue}d past due" if overdue else e(row["due_date"])
        note = e(row["last_note"]) if row["last_note"] else "<span class='muted'>No progress note</span>"
        progress = f"""<div class='note-preview'>{note}</div>
        <form class='quick-note' method='post' action='/occurrence/{row["id"]}/progress'>
          <input name='detail' placeholder='Progress note' required>
          <button>Save</button>
        </form>"""
        table_rows.append(
            f"""<tr>
            <td><a href='/occurrence/{row['id']}'>{e(row['case_number'])}</a><br><span class='muted'>{e(row['rma_number'])}</span></td>
            <td>{e(row['type_name'])}</td><td>{e(row['title'])}</td>
            <td>{e(row['owner_name'] or row['owner_email'])}</td>
            <td><span class='status'>{e(row['status'])}</span></td>
            <td class='{"bad" if overdue else ""}'>{age_text}</td>
            <td>{e(row['next_action'])}</td><td>{progress}</td>
            </tr>"""
        )
    tr = "".join(table_rows)

    type_options = "<option value=''>All types</option>" + "".join(
        f"<option {'selected' if type_filter==x['name'] else ''}>{e(x['name'])}</option>" for x in types
    )
    status_options = "<option value=''>All open statuses</option>" + "".join(
        f"<option {'selected' if status_filter==x else ''}>{e(x)}</option>" for x in STATUSES if x != "CLOSED"
    )
    filters = f"""<form method='get' class='form panel'>
      <label>Search<input name='q' value='{e(q)}' placeholder='Case, RMA number, customer, part, owner'></label>
      <label>Type<select name='type'>{type_options}</select></label>
      <label>Status<select name='status'>{status_options}</select></label>
      <div><br><button>Filter</button> <a class='btn secondary' href='/'>Clear</a></div>
    </form>"""

    return page(
        "Dashboard",
        f"""<h1>Dashboard</h1><div class='grid'>{cards}</div>
        <div class='section-head' style='margin-top:20px'><h2 style='margin:0'>Past Due Aging</h2></div>
        <div class='aging-grid'>{heat}</div>
        <div class='toolbar'><a class='btn' href='/occurrence/new'>New occurrence</a>
        <a class='btn secondary' href='/expedite/run'>Run notifications</a></div>
        {filters}<br><div class='panel table'><table><tr><th>Case</th><th>Type</th><th>Occurrence</th>
        <th>Owner</th><th>Status</th><th>Due / Age</th><th>Next action</th><th>Progress</th></tr>
        {tr or '<tr><td colspan=8>No matching open occurrences.</td></tr>'}</table></div>""",
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


@bp.route("/appearance", methods=["GET", "POST"])
def appearance():
    keys = {
        "theme_accent": "#1F6FBC",
        "theme_accent_strong": "#0B3A75",
        "theme_background": "#090B0E",
        "theme_panel": "#11161C",
        "theme_card": "#171E26",
        "theme_text": "#F4F7FB",
        "theme_muted": "#9BA8B7",
    }
    with connect(db_path()) as con:
        if request.method == "POST":
            for key, fallback in keys.items():
                set_setting(con, key, safe_hex(request.form.get(key, fallback), fallback))
            flash("Appearance saved.")
            return redirect(url_for("core.appearance"))
        values = {key: get_setting(con, key, fallback) for key, fallback in keys.items()}
    fields = "".join(
        f"<label>{e(label)}<input type='color' name='{key}' value='{e(values[key])}'></label>"
        for key, label in [
            ("theme_accent", "Accent blue"),
            ("theme_accent_strong", "Deep blue"),
            ("theme_background", "Background"),
            ("theme_panel", "Panel"),
            ("theme_card", "Card"),
            ("theme_text", "Text"),
            ("theme_muted", "Muted text"),
        ]
    )
    return page("Appearance", f"""<h1>Appearance</h1><form method='post' class='panel'>
      <div class='color-row'>{fields}</div><div class='toolbar'><button>Save</button></div>
    </form>""")


@bp.route("/rma/workflow", methods=["GET", "POST"])
def rma_workflow_settings():
    role_fields = [
        ("csr", "Customer Service"),
        ("shipping", "Shipping"),
        ("quality", "Quality"),
    ]
    cc_fields = [
        ("quality", "Quality"),
        ("operations", "Operations"),
        ("customer_service", "Customer Service"),
        ("design", "Design"),
    ]
    with connect(db_path()) as con:
        if request.method == "POST":
            for key, _label in role_fields:
                for suffix in ("", "_2"):
                    set_setting(con, f"rma_role_{key}_name{suffix}", request.form.get(f"{key}_name{suffix}", "").strip())
                    set_setting(con, f"rma_role_{key}_email{suffix}", request.form.get(f"{key}_email{suffix}", "").strip().lower())
            for key, _label in cc_fields:
                set_setting(con, f"rma_cc_{key}", request.form.get(f"cc_{key}", "").strip().lower())
            flash("RMA workflow recipients saved.")
            return redirect(url_for("core.rma_workflow_settings"))
        role_values = {}
        for key, _label in role_fields:
            for suffix in ("", "_2"):
                role_values[f"{key}_name{suffix}"] = get_setting(con, f"rma_role_{key}_name{suffix}", "")
                role_values[f"{key}_email{suffix}"] = get_setting(con, f"rma_role_{key}_email{suffix}", "")
        cc_values = {key: get_setting(con, f"rma_cc_{key}", "") for key, _ in cc_fields}

    roles = "".join(
        f"""<div class='card'><h2>{e(label)}</h2><div class='form'>
        <label>Primary 1 name<input name='{key}_name' value='{e(role_values[key+"_name"])}'></label>
        <label>Primary 1 email<input type='email' name='{key}_email' value='{e(role_values[key+"_email"])}'></label>
        <label>Primary 2 name<input name='{key}_name_2' value='{e(role_values[key+"_name_2"])}'></label>
        <label>Primary 2 email<input type='email' name='{key}_email_2' value='{e(role_values[key+"_email_2"])}'></label>
        </div></div>"""
        for key, label in role_fields
    )
    ccs = "".join(
        f"<label>{e(label)} CC<input name='cc_{key}' value='{e(cc_values[key])}' placeholder='email@example.com; second@example.com'></label>"
        for key, label in cc_fields
    )
    return page("RMA Workflow", f"""<h1>RMA Workflow</h1><form method='post'>
      <div class='grid'>{roles}</div><br><div class='panel'><h2>Read-only CC recipients</h2>
      <div class='form'>{ccs}</div></div><div class='toolbar'><button>Save</button></div>
    </form>""")


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
                assign_stage_owner(con, oid, "INTAKE")
                con.execute(
                    "UPDATE occurrences SET next_action=?,updated_at=? WHERE id=?",
                    (stage_info("INTAKE").action, utcnow(), oid),
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
