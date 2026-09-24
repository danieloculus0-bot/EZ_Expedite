from __future__ import annotations

import os
from urllib.parse import urljoin

import requests
from flask import current_app, request, session

from .db import connect, get_setting
from .helpers import db_path

SCOPES = ["User.Read"]


class AuthConfigError(RuntimeError):
    pass


def _settings() -> dict:
    with connect(db_path()) as con:
        return {
            "client_id": os.environ.get("M365_CLIENT_ID") or get_setting(con, "m365_client_id", ""),
            "tenant": os.environ.get("M365_TENANT") or get_setting(con, "m365_tenant", "organizations"),
            "client_secret": os.environ.get("M365_CLIENT_SECRET") or get_setting(con, "m365_client_secret", ""),
            "public_base_url": os.environ.get("EZ_EXPEDITE_PUBLIC_BASE_URL") or get_setting(con, "public_base_url", ""),
        }


def redirect_uri() -> str:
    cfg = _settings()
    base = cfg["public_base_url"].strip()
    if not base:
        base = request.url_root
    return urljoin(base.rstrip("/") + "/", "auth/callback")


def confidential_app():
    cfg = _settings()
    if not cfg["client_id"]:
        raise AuthConfigError("Microsoft Application Client ID is not configured.")
    if not cfg["client_secret"]:
        raise AuthConfigError("Microsoft web sign-in secret is not configured.")
    try:
        import msal
    except ImportError as exc:
        raise AuthConfigError("MSAL is not installed.") from exc
    return msal.ConfidentialClientApplication(
        cfg["client_id"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant'] or 'organizations'}",
        client_credential=cfg["client_secret"],
    )


def begin_sign_in() -> str:
    flow = confidential_app().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=redirect_uri(),
        prompt="select_account",
    )
    if "auth_uri" not in flow:
        raise AuthConfigError(flow.get("error_description") or "Microsoft sign-in could not be started.")
    session["auth_flow"] = flow
    return flow["auth_uri"]


def complete_sign_in(auth_response: dict) -> dict:
    flow = session.pop("auth_flow", None)
    if not flow:
        raise AuthConfigError("Microsoft sign-in session expired. Start sign-in again.")
    try:
        result = confidential_app().acquire_token_by_auth_code_flow(flow, auth_response)
    except ValueError as exc:
        raise AuthConfigError("Microsoft sign-in response could not be validated.") from exc
    if "access_token" not in result:
        raise AuthConfigError(result.get("error_description") or result.get("error") or "Microsoft sign-in failed.")

    claims = result.get("id_token_claims") or {}
    graph = requests.get(
        "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
        headers={"Authorization": f"Bearer {result['access_token']}"},
        timeout=20,
    )
    if graph.status_code >= 400:
        raise AuthConfigError(f"Microsoft Graph sign-in verification failed ({graph.status_code}).")
    me = graph.json()
    user = {
        "id": me.get("id") or claims.get("oid") or "",
        "displayName": me.get("displayName") or claims.get("name") or "",
        "mail": me.get("mail") or me.get("userPrincipalName") or claims.get("preferred_username") or "",
        "userPrincipalName": me.get("userPrincipalName") or claims.get("preferred_username") or "",
    }
    session["user"] = user
    return user


def signed_in_user() -> dict | None:
    user = session.get("user")
    return user if isinstance(user, dict) else None


def sign_out() -> None:
    session.pop("user", None)
    session.pop("auth_flow", None)
