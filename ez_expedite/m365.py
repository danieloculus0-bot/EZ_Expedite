from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import requests

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "User.Read",
    "User.ReadBasic.All",
    "Mail.Read",
    "Mail.Send",
    "Chat.Create",
    "ChatMessage.Send",
]


class M365Error(RuntimeError):
    pass


class M365Client:
    """Microsoft 365 delegated client.

    EZ Expedite never asks for or stores a Microsoft password. Authentication is
    handled by Microsoft through MSAL. The local token cache is stored under the
    instance directory, which is gitignored and must be treated as sensitive.
    """

    def __init__(self, client_id: str, tenant: str, cache_path: str | Path):
        if not client_id:
            raise M365Error("Microsoft 365 application client ID is not configured.")
        try:
            import msal
        except ImportError as exc:
            raise M365Error("The msal package is not installed. Run pip install -r requirements.txt.") from exc
        self.msal = msal
        self.client_id = client_id
        self.tenant = tenant or "organizations"
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                self.cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant}",
            token_cache=self.cache,
        )

    def _persist(self) -> None:
        if self.cache.has_state_changed:
            self.cache_path.write_text(self.cache.serialize(), encoding="utf-8")

    def connect_interactive(self) -> dict:
        result = self.app.acquire_token_interactive(scopes=SCOPES, prompt="select_account")
        self._persist()
        if "access_token" not in result:
            raise M365Error(result.get("error_description") or result.get("error") or "Microsoft sign-in failed.")
        return result

    def disconnect(self) -> None:
        if self.cache_path.exists():
            self.cache_path.unlink()
        self.cache = self.msal.SerializableTokenCache()

    def token(self) -> str:
        accounts = self.app.get_accounts()
        if not accounts:
            raise M365Error("Microsoft 365 is not connected.")
        result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
        self._persist()
        if not result or "access_token" not in result:
            raise M365Error("Microsoft 365 authorization needs to be renewed.")
        return result["access_token"]

    def request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token()}"
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        response = requests.request(method, GRAPH_ROOT + path, headers=headers, timeout=30, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise M365Error(f"Microsoft Graph {response.status_code}: {detail}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def me(self) -> dict:
        return self.request("GET", "/me?$select=id,displayName,mail,userPrincipalName")

    def recent_inbox(self, top: int = 25) -> list[dict]:
        top = max(1, min(int(top), 50))
        data = self.request(
            "GET",
            f"/me/mailFolders/inbox/messages?$top={top}&$orderby=receivedDateTime%20desc&$select=id,subject,from,receivedDateTime,bodyPreview,webLink",
        )
        return data.get("value", []) if isinstance(data, dict) else []

    def message(self, message_id: str) -> dict:
        return self.request(
            "GET",
            f"/me/messages/{quote(message_id, safe='')}?$select=id,subject,from,receivedDateTime,bodyPreview,webLink,body",
        )

    def send_mail(self, to_address: str, subject: str, body: str) -> None:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_address}}],
            },
            "saveToSentItems": True,
        }
        self.request("POST", "/me/sendMail", json=payload)

    def find_user(self, email_or_upn: str) -> dict:
        value = quote(email_or_upn.strip(), safe="@._-")
        return self.request("GET", f"/users/{value}?$select=id,displayName,mail,userPrincipalName")

    def ensure_one_on_one_chat(self, recipient_email: str) -> str:
        me = self.me()
        other = self.find_user(recipient_email)
        payload = {
            "chatType": "oneOnOne",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{me['id']}')",
                },
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{other['id']}')",
                },
            ],
        }
        chat = self.request("POST", "/chats", json=payload)
        return chat["id"]

    def send_teams_message(self, recipient_email: str, text: str) -> str:
        chat_id = self.ensure_one_on_one_chat(recipient_email)
        message = self.request(
            "POST",
            f"/chats/{quote(chat_id, safe='')}/messages",
            json={"body": {"contentType": "text", "content": text}},
        )
        return message.get("id", "") if isinstance(message, dict) else ""
