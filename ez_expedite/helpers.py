from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path

from flask import current_app, render_template_string

from .db import connect, get_setting
from .m365 import M365Client

STATUSES = [
    "NEW",
    "ASSIGNMENT REQUIRED",
    "INVESTIGATING",
    "AWAITING MATERIAL",
    "AWAITING CUSTOMER",
    "AWAITING INTERNAL ACTION",
    "CORRECTIVE ACTION OPEN",
    "AWAITING RECOVERY",
    "READY TO CLOSE",
    "CLOSED",
]
PRIORITIES = ["Low", "Normal", "High", "Critical"]

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def safe_hex(value: str, fallback: str) -> str:
    value = str(value or "").strip()
    return value.upper() if _HEX.match(value) else fallback


CSS = r"""
*{box-sizing:border-box}
html{background:var(--bg);color-scheme:dark}
body{
  margin:0;background:var(--bg);color:var(--text);
  font:14px/1.45 "Segoe UI Variable","Segoe UI",-apple-system,BlinkMacSystemFont,Arial,sans-serif;
  letter-spacing:.002em
}
a{color:var(--accent-soft);text-decoration:none}
a:hover{color:var(--text)}
.appbar{
  position:sticky;top:0;z-index:30;
  display:flex;align-items:center;gap:18px;min-height:64px;padding:10px 22px;
  background:rgba(9,11,14,.93);backdrop-filter:blur(18px);
  border-bottom:1px solid var(--line);box-shadow:0 8px 30px rgba(0,0,0,.15)
}
.brandblock{display:flex;align-items:center;gap:10px;white-space:nowrap}
.brandmark{width:10px;height:30px;border-radius:999px;background:var(--accent)}
.brand{font-size:20px;font-weight:760;letter-spacing:-.025em;color:var(--text)}

nav{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
nav a{
  color:var(--muted);padding:7px 9px;border-radius:10px;font-size:13px;
  transition:background .15s ease,color .15s ease
}
nav a:hover{background:var(--card);color:var(--text)}
.grow{flex:1}.muted{color:var(--muted)}.small{font-size:12px}
main{max-width:1540px;margin:0 auto;padding:28px 24px 50px}
h1,h2,h3{margin-top:0;letter-spacing:-.025em}
h1{font-size:30px;font-weight:760;margin-bottom:18px}
h2{font-size:17px;font-weight:720;margin-bottom:14px}
h3{font-size:14px;font-weight:700}
.grid,.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.panel,.card{
  background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:18px;
  box-shadow:0 16px 45px rgba(0,0,0,.16)
}
.card{background:var(--card)}
.metric{min-height:102px;display:flex;flex-direction:column;justify-content:space-between}
.metric span{color:var(--muted);font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.055em}
.metric b{font-size:30px;line-height:1;font-weight:740;letter-spacing:-.035em}
.wide{grid-column:1/-1}
label{display:block;font-size:12px;color:var(--muted);font-weight:620}
input,select,textarea{
  width:100%;margin-top:6px;padding:10px 11px;background:var(--input);color:var(--text);
  border:1px solid var(--line-strong);border-radius:11px;outline:none;
  font:inherit;transition:border .15s ease,box-shadow .15s ease,background .15s ease
}
input:focus,select:focus,textarea:focus{
  border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-haze);background:var(--input-focus)
}
textarea{min-height:96px;resize:vertical}
input[type=checkbox]{width:17px;height:17px;margin:0 7px 0 0;vertical-align:-3px;accent-color:var(--accent)}
input[type=color]{height:42px;padding:4px}
.btn,button{
  appearance:none;display:inline-flex;align-items:center;justify-content:center;gap:6px;
  border:1px solid var(--accent);border-radius:11px;background:var(--accent);color:white;
  font:700 13px/1 "Segoe UI Variable","Segoe UI",Arial,sans-serif;
  padding:10px 14px;cursor:pointer;box-shadow:none;
  transition:filter .14s ease,transform .06s ease,background .14s ease,border .14s ease
}
.btn:hover,button:hover{filter:brightness(1.10);color:white}
.btn:active,button:active{transform:translateY(1px)}
.secondary{
  background:var(--button-muted)!important;border-color:var(--line-strong)!important;color:var(--text)!important
}
.danger{
  background:transparent!important;border-color:var(--line-strong)!important;color:var(--text)!important
}
.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:14px 0}
.table{overflow:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{
  color:var(--muted);font-size:11px;font-weight:720;text-transform:uppercase;
  letter-spacing:.055em;white-space:nowrap
}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--row-hover)}
.status{
  display:inline-block;background:var(--accent-haze);border:1px solid var(--accent-line);
  color:var(--accent-soft);border-radius:999px;padding:4px 9px;font-size:11px;font-weight:720;letter-spacing:.025em
}
.flash,.notice{
  padding:12px 14px;border:1px solid var(--accent-line);border-radius:14px;
  background:var(--notice);margin-bottom:14px;color:var(--text)
}
.bad{
  color:var(--text);font-weight:720;
  text-decoration:underline;text-decoration-color:var(--accent);text-underline-offset:4px
}
.split{display:grid;grid-template-columns:minmax(0,2fr) minmax(290px,1fr);gap:14px}
.event{
  width:fit-content;max-width:94%;margin:0 0 10px auto;padding:10px 13px;
  background:var(--message);border:1px solid var(--line);border-radius:17px 17px 5px 17px;
  box-shadow:0 5px 18px rgba(0,0,0,.09)
}
.event b{font-size:12px;color:var(--accent-soft)}
.event .muted{font-size:11px}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.kicker{
  color:var(--accent-soft);font-size:11px;font-weight:760;text-transform:uppercase;letter-spacing:.08em
}
.stage-rail{
  display:grid;grid-template-columns:repeat(5,1fr);gap:0;margin:2px 0 18px;
  background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden
}
.stage-step{
  position:relative;min-height:88px;padding:15px 15px 13px;border-right:1px solid var(--line)
}
.stage-step:last-child{border-right:0}
.stage-step:before{
  content:"";position:absolute;left:15px;right:15px;bottom:0;height:3px;border-radius:999px;background:var(--line-strong)
}
.stage-step.done:before,.stage-step.current:before{background:var(--accent)}
.stage-step.current{background:var(--accent-haze)}
.stage-num{
  display:block;color:var(--muted);font-size:10px;font-weight:760;letter-spacing:.08em;text-transform:uppercase
}
.stage-step strong{display:block;margin-top:5px;font-size:13px;line-height:1.25}
.stage-step small{display:block;margin-top:5px;color:var(--muted);font-size:11px}
.stage-step.future{opacity:.52}
.stage-action{
  display:flex;justify-content:space-between;gap:16px;align-items:center;
  padding:16px 18px;background:var(--card);border:1px solid var(--line);border-radius:16px;margin-bottom:16px
}
.stage-action p{margin:4px 0 0;color:var(--muted)}
.workflow-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.segmented{display:flex;gap:5px;padding:4px;background:var(--input);border:1px solid var(--line);border-radius:12px}
.segmented label{flex:1;margin:0}
.segmented input{display:none}
.segmented span{
  display:block;text-align:center;padding:8px 10px;border-radius:8px;color:var(--muted);cursor:pointer;
  font-size:12px;font-weight:700
}
.segmented input:checked+span{background:var(--accent);color:white}
.color-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.aging-grid{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:8px;margin:12px 0 18px}
.aging-cell{border:1px solid var(--accent-line);border-radius:15px;padding:14px;min-height:82px}
.aging-cell span{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.055em;font-weight:720}
.aging-cell b{display:block;margin-top:7px;font-size:25px;line-height:1;font-weight:760}
.heat-1{background:rgba(31,111,188,.08)}
.heat-2{background:rgba(31,111,188,.14)}
.heat-3{background:rgba(31,111,188,.22)}
.heat-4{background:rgba(31,111,188,.32)}
.heat-5{background:rgba(31,111,188,.46)}
.quick-note{display:flex;gap:6px;min-width:260px}
.quick-note input{margin:0;min-width:180px}
.quick-note button{padding:9px 11px}
.note-preview{max-width:360px;color:var(--text);font-size:12px;margin-bottom:7px}
.action-card{background:var(--card);border:1px solid var(--accent-line);border-radius:18px;padding:18px;margin-bottom:16px}
.action-card.readonly{border-color:var(--line);opacity:.92}
.action-meta{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;color:var(--muted);font-size:12px}
.action-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.delegate-list{display:flex;gap:6px;flex-wrap:wrap}
.delegate-chip{border:1px solid var(--line-strong);background:var(--input);border-radius:999px;padding:5px 9px;font-size:11px;color:var(--muted)}
.empty{color:var(--muted);padding:22px;text-align:center}
@media(max-width:1050px){
  .appbar{align-items:flex-start}.tagline{display:none}
  .stage-rail{grid-template-columns:1fr}.stage-step{min-height:auto;border-right:0;border-bottom:1px solid var(--line)}
  .stage-step:last-child{border-bottom:0}
}
@media(max-width:850px){
  main{padding:18px 14px 40px}.split,.workflow-grid{grid-template-columns:1fr}.table{overflow:auto}
  .appbar{padding:10px 14px}.stage-action{align-items:flex-start;flex-direction:column}
  .aging-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}
  .action-fields{grid-template-columns:1fr}
}
"""

BASE = """<!doctype html>
<html>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta name='color-scheme' content='dark'>
<title>{{title}} | EZ Expedite</title>
<style>{{css}}{{theme_css}}</style>
</head>
<body>
<header class='appbar'>
  <div class='brandblock'><span class='brandmark'></span><a class='brand' href='/'>EZ Expedite</a></div>
  <nav>
    <a href='/'>Dashboard</a><a href='/occurrence/new'>New</a><a href='/types'>Types</a>
    <a href='/import/generic'>Import</a><a href='/import/rma'>RMA Import</a>
    <a href='/rma/workflow'>RMA Workflow</a><a href='/systems'>ERP / Systems</a>
    <a href='/mail/inbox'>Outlook</a><a href='/appearance'>Appearance</a><a href='/setup'>Microsoft 365</a>
  </nav>
  <div class='grow'></div><span class='muted small'>{{user_label}}</span><a class='small' href='{{auth_href}}'>{{auth_label}}</a>
</header>
<main>
{% for m in get_flashed_messages() %}<div class='flash'>{{m}}</div>{% endfor %}
{{body|safe}}
</main>
</body>
</html>"""


def e(v):
    return escape("" if v is None else str(v))


def fnum(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def truth(v):
    return 1 if str(v or "").lower() in {"1", "true", "yes", "on", "y"} else 0


def db_path():
    return Path(current_app.config["DB_PATH"])


def m365():
    with connect(db_path()) as con:
        cid = os.environ.get("M365_CLIENT_ID") or get_setting(con, "m365_client_id")
        tenant = os.environ.get("M365_TENANT") or get_setting(con, "m365_tenant", "organizations")
    return M365Client(cid, tenant, Path(current_app.config["TOKEN_CACHE"]))


def profile():
    with connect(db_path()) as con:
        multi_user = get_setting(con, "multi_user_mode", "1") == "1"
    if multi_user:
        try:
            from .auth import signed_in_user
            return signed_in_user()
        except Exception:
            return None
    try:
        return m365().me()
    except Exception:
        return None


def theme_css() -> str:
    with connect(db_path()) as con:
        accent = safe_hex(get_setting(con, "theme_accent", "#1F6FBC"), "#1F6FBC")
        accent_strong = safe_hex(get_setting(con, "theme_accent_strong", "#0B3A75"), "#0B3A75")
        bg = safe_hex(get_setting(con, "theme_background", "#090B0E"), "#090B0E")
        panel = safe_hex(get_setting(con, "theme_panel", "#11161C"), "#11161C")
        card = safe_hex(get_setting(con, "theme_card", "#171E26"), "#171E26")
        text = safe_hex(get_setting(con, "theme_text", "#F4F7FB"), "#F4F7FB")
        muted = safe_hex(get_setting(con, "theme_muted", "#9BA8B7"), "#9BA8B7")
    return f""":root{{
      --bg:{bg};--panel:{panel};--card:{card};--text:{text};--muted:{muted};
      --accent:{accent};--accent-strong:{accent_strong};--accent-soft:#8FC6F2;
      --accent-haze:rgba(31,111,188,.14);--accent-line:rgba(31,111,188,.38);
      --line:#242B33;--line-strong:#35404C;--input:#0D1116;--input-focus:#101720;
      --button-muted:#27313B;--row-hover:rgba(255,255,255,.025);
      --notice:rgba(31,111,188,.09);--message:#1B2632;
    }}"""


def page(title, body):
    p = profile()
    if p:
        user_label = p.get("displayName") or p.get("mail") or p.get("userPrincipalName") or ""
        auth_label = "Sign out"
        auth_href = "/auth/logout"
    else:
        user_label = ""
        auth_label = "Sign in"
        auth_href = "/auth/login"
    return render_template_string(
        BASE,
        title=title,
        body=body,
        css=CSS,
        theme_css=theme_css(),
        user_label=e(user_label),
        auth_label=auth_label,
        auth_href=auth_href,
    )


def setup_done():
    with connect(db_path()) as con:
        return get_setting(con, "setup_complete", "0") == "1"
