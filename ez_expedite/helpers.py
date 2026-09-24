from __future__ import annotations

import os
from html import escape
from pathlib import Path

from flask import current_app, render_template_string

from .db import connect, get_setting
from .m365 import M365Client

STATUSES=["NEW","ASSIGNMENT REQUIRED","INVESTIGATING","AWAITING MATERIAL","AWAITING CUSTOMER","AWAITING INTERNAL ACTION","CORRECTIVE ACTION OPEN","AWAITING RECOVERY","READY TO CLOSE","CLOSED"]
PRIORITIES=["Low","Normal","High","Critical"]
CSS=""":root{color-scheme:dark;--bg:#0c1117;--p:#141b23;--l:#2a3642;--t:#e8eef5;--m:#93a4b5;--a:#55a8dc;--bad:#e46c6c}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:14px Segoe UI,Arial}a{color:#7bc4ef;text-decoration:none}header{background:#090e13;border-bottom:1px solid var(--l);padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}.brand{font-size:20px;font-weight:800;color:white}nav{display:flex;gap:8px;flex-wrap:wrap}nav a{color:#b8c5d1}.grow{flex:1}.muted{color:var(--m)}main{max-width:1500px;margin:auto;padding:20px}.grid,.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.card,.panel{background:var(--p);border:1px solid var(--l);border-radius:12px;padding:14px}.metric b{font-size:27px;display:block;margin-top:5px}.wide{grid-column:1/-1}input,select,textarea{width:100%;padding:9px;background:#0a1016;color:var(--t);border:1px solid #344250;border-radius:8px}textarea{min-height:90px}label{font-size:12px;color:#aab8c5}.btn,button{display:inline-block;border:0;border-radius:8px;background:var(--a);color:#07131d;font-weight:700;padding:9px 12px;cursor:pointer}.secondary{background:#344454!important;color:white!important}.danger{background:#9c4747!important;color:white!important}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--l);vertical-align:top}th{color:var(--m)}.status{background:#263545;border-radius:999px;padding:4px 8px;font-size:11px}.flash,.notice{padding:10px;border:1px solid #496173;border-radius:9px;background:#12202a;margin-bottom:12px}.bad{color:var(--bad)}.split{display:grid;grid-template-columns:2fr 1fr;gap:12px}.event{border-left:2px solid #304353;padding-left:10px;margin:0 0 12px}@media(max-width:850px){.split{grid-template-columns:1fr}.table{overflow:auto}}"""
BASE="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{title}} | EZ Expedite</title><style>{{css}}</style></head><body><header><a class='brand' href='/'>EZ Expedite</a><span class='muted'>Own it. Move it. Close it.</span><nav><a href='/'>Dashboard</a><a href='/occurrence/new'>New</a><a href='/types'>Types</a><a href='/import/generic'>Import Anything</a><a href='/import/rma'>RMA Import</a><a href='/systems'>ERP / Systems</a><a href='/mail/inbox'>Outlook Inbox</a><a href='/setup'>Microsoft 365</a></nav><div class='grow'></div><span class='muted'>{{m365}}</span></header><main>{% for m in get_flashed_messages() %}<div class='flash'>{{m}}</div>{% endfor %}{{body|safe}}</main></body></html>"""

def e(v): return escape("" if v is None else str(v))
def fnum(v):
    try:return float(v or 0)
    except(TypeError,ValueError):return 0.0
def truth(v):return 1 if str(v or "").lower() in {"1","true","yes","on","y"} else 0

def db_path():return Path(current_app.config["DB_PATH"])
def m365():
    with connect(db_path()) as con:
        cid=os.environ.get("M365_CLIENT_ID") or get_setting(con,"m365_client_id")
        tenant=os.environ.get("M365_TENANT") or get_setting(con,"m365_tenant","organizations")
    return M365Client(cid,tenant,Path(current_app.config["TOKEN_CACHE"]))
def profile():
    try:return m365().me()
    except Exception:return None
def page(title,body):
    p=profile(); label=(p.get("displayName") or p.get("userPrincipalName")) if p else "not connected"
    return render_template_string(BASE,title=title,body=body,css=CSS,m365="M365: "+e(label))
def setup_done():
    with connect(db_path()) as con:return get_setting(con,"setup_complete","0")=="1"
