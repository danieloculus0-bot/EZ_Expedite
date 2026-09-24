from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, redirect, request, url_for

from .auth import signed_in_user
from .db import connect, get_setting, init_db
from .helpers import setup_done
from .routes_core import bp as core_bp
from .routes_integrations import bp as integrations_bp
from .routes_occurrence import bp as occurrence_bp


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home()) / "EZ_Expedite"
    return Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    app = Flask(__name__)
    root = _runtime_root()
    instance = root / "instance"
    instance.mkdir(parents=True, exist_ok=True)
    secret = instance / "flask_secret.txt"
    if not secret.exists():
        secret.write_text(os.urandom(32).hex(), encoding="utf-8")
    app.secret_key = os.environ.get("EZ_EXPEDITE_SECRET") or secret.read_text(encoding="utf-8")
    app.config.update(
        DB_PATH=str(instance / "ez_expedite.db"),
        UPLOAD_FOLDER=str(instance / "uploads"),
        TOKEN_CACHE=str(instance / "m365_token_cache.json"),
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,
        RUNTIME_ROOT=str(root),
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DB_PATH"])
    app.register_blueprint(core_bp)
    app.register_blueprint(occurrence_bp)
    app.register_blueprint(integrations_bp)

    @app.before_request
    def access_gate():
        endpoint = request.endpoint or ""
        setup_exempt = {"core.setup", "core.m365_connect", "health", "static"}
        auth_exempt = {"core.auth_login", "core.auth_callback", "core.auth_logout"}
        if endpoint not in setup_exempt and endpoint not in auth_exempt and not setup_done():
            return redirect(url_for("core.setup"))

        if not setup_done():
            return None

        with connect(app.config["DB_PATH"]) as con:
            multi_user = get_setting(con, "multi_user_mode", "1") == "1"

        if not multi_user:
            return None

        if endpoint in auth_exempt or endpoint == "health":
            return None

        if endpoint in {"core.setup", "core.m365_connect"}:
            if request.remote_addr in {"127.0.0.1", "::1"}:
                return None
            if signed_in_user():
                return None
            return redirect(url_for("core.auth_login"))

        if not signed_in_user():
            return redirect(url_for("core.auth_login"))
        return None

    @app.route("/health")
    def health():
        return {"status": "ok", "app": "EZ Expedite"}

    return app
