"""The only actions the agent can take. There is deliberately NO send, delete or fetch-URL tool.

Mailbox backends:
- LocalMailbox: reads a JSON file of emails, writes drafts to out/drafts/ (default; no account needed)
- GmailMailbox: Gmail API, read + create draft only (optional; see README → Gmail)
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .models import Email


class LocalMailbox:
    def __init__(self, path: str, out_dir: str = "out"):
        self.path, self.out = Path(path), Path(out_dir)

    def list_unread(self, limit: int = 50) -> list[Email]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Email(**e) for e in data[:limit]]

    def create_draft(self, email: Email, body: str) -> str:
        d = self.out / "drafts"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{email.id}.txt"
        p.write_text(f"To: {email.sender}\nSubject: Re: {email.subject}\n\n{body}\n", encoding="utf-8")
        return str(p)


class GmailMailbox:  # pragma: no cover - needs real OAuth credentials
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"]

    def __init__(self, credentials_file: str = "credentials.json", token_file: str = "token.json"):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_file, self.SCOPES) if os.path.exists(token_file) else None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = InstalledAppFlow.from_client_secrets_file(credentials_file, self.SCOPES).run_local_server(port=0)
            Path(token_file).write_text(creds.to_json())
        self.svc = build("gmail", "v1", credentials=creds)

    def list_unread(self, limit: int = 25) -> list[Email]:
        import base64
        res = self.svc.users().messages().list(userId="me", q="is:unread in:inbox newer_than:2d", maxResults=limit).execute()
        out = []
        for m in res.get("messages", []):
            msg = self.svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
            h = {x["name"]: x["value"] for x in msg["payload"].get("headers", [])}
            body = msg.get("snippet", "")
            for part in [msg["payload"], *msg["payload"].get("parts", [])]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
                    break
            ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000).astimezone().isoformat(timespec="minutes")
            out.append(Email(m["id"], h.get("From", ""), h.get("Subject", ""), body, ts,
                             {k: v for k, v in h.items() if k.lower() == "list-unsubscribe"}))
        return out

    def create_draft(self, email: Email, body: str) -> str:
        import base64
        from email.mime.text import MIMEText
        mime = MIMEText(body)
        mime["to"], mime["subject"] = email.sender, f"Re: {email.subject}"
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        d = self.svc.users().drafts().create(userId="me", body={"message": {"raw": raw, "threadId": email.id}}).execute()
        return f"gmail-draft:{d['id']}"
    # NOTE: no send(), no delete(), no modify(). The gmail.compose scope technically allows sending;
    # this code never calls it, and the README lists that as a known limitation.


class TaskList:
    def __init__(self, out_dir: str = "out"):
        self.path = Path(out_dir) / "tasks.json"

    def create_task(self, title: str, due: str | None, priority: str) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tasks = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
        task = {"title": title, "due": due, "priority": priority, "created": datetime.now().isoformat(timespec="minutes")}
        if not any(t["title"] == title and t["due"] == due for t in tasks):  # idempotent re-runs
            tasks.append(task)
            self.path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
        return task


class Log:
    def __init__(self, out_dir: str = "out"):
        self.path = Path(out_dir) / "run_log.jsonl"

    def record(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **event}, ensure_ascii=False) + "\n")


def send_telegram(text: str) -> bool:
    """Deliver the briefing to Kevin's own private Telegram chat (optional)."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "parse_mode": "Markdown"}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30) as r:  # noqa: S310
        return r.status == 200
