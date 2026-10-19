"""Rules-only classifier.

Used three ways:
- as a security pre-check before the LLM (SUSPICIOUS can't be overridden),
- as a fallback when the LLM output is invalid twice,
- as the no-API-key baseline (`--provider rules`) that the eval compares the LLM against.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .guardrails import phishing_score
from .models import Email, Triage

_ACADEMIC = re.compile(r"(?i)(\.ac\.id\b|\.edu\b|\b(binus|university|universitas|campus|lecturer|dosen|exams?|ujian|midterm"
                       r"|uts|uas|assignment|tugas|krs|semester|course|kuliah|skripsi|thesis)\b)")
_TECH = re.compile(r"(?i)(github|vercel|netlify|aws|cloudflare|render|railway|digitalocean|build failed|deploy"
                   r"|invoice paid|payment received|billing|uptime|incident|dependabot|security alert)")
_NEWS = re.compile(r"(?i)(unsubscribe|newsletter|weekly digest|\btop \d+\b|webinar|\d+% off|flash sale)")
_CLIENT = re.compile(r"(?i)(client|project|bug ?fix|fix|website|app|quote|proposal|freelance|deadline|asap|urgent"
                     r"|meeting|revision|milestone|feedback|klien|proyek)")
_REPLY_NEEDED = re.compile(r"(?i)(\?|please (reply|confirm|let me know)|can you|could you|are you available|bisa)")

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def extract_deadline(text: str, received: str) -> str | None:
    """Very small date parser: ISO dates, 'tomorrow', 'today', weekday names, '19 Oct'."""
    base = _parse_iso(received) or datetime.now()
    m = re.search(r"\b(20\d\d-\d\d-\d\d)(?:[ T](\d\d:\d\d))?", text)
    if m:
        return m.group(1) + (f"T{m.group(2)}" if m.group(2) else "")
    t = re.search(r"(?i)\b(\d{1,2})(?:[:.](\d\d))?\s*(am|pm)\b", text)
    hour = None
    if t:
        hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
    if re.search(r"(?i)\btomorrow|besok\b", text):
        d = base + timedelta(days=1)
        return d.strftime("%Y-%m-%d") + (f"T{hour:02d}:00" if hour is not None else "")
    if re.search(r"(?i)\b(today|tonight|end of day|eod|hari ini)\b", text):
        return base.strftime("%Y-%m-%d") + (f"T{hour:02d}:00" if hour is not None else "")
    for i, wd in enumerate(_WEEKDAYS):
        if re.search(rf"(?i)\b{wd}\b", text):
            ahead = (i - base.weekday()) % 7 or 7
            return (base + timedelta(days=ahead)).strftime("%Y-%m-%d")
    m = re.search(r"(?i)\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", text)
    if m:
        months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
        mon = months.index(m.group(2).lower()[:3]) + 1
        year = base.year + (1 if mon < base.month else 0)
        return f"{year}-{mon:02d}-{int(m.group(1)):02d}"
    return None


def _parse_iso(s: str):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def classify(email: Email) -> Triage:
    text = f"{email.subject}\n{email.body}"
    score, reasons = phishing_score(email)
    if score >= 2:
        return Triage(email.id, "SUSPICIOUS", f"Possible phishing: {', '.join(reasons)}.",
                      action_item="Do not click links; report/delete manually.", source="rules")
    has_unsub = "list-unsubscribe" in {k.lower() for k in email.headers}
    if has_unsub or _NEWS.search(text):
        cat = "LOW_PRIORITY"
    elif _ACADEMIC.search(text + " " + email.sender_domain):
        cat = "ACADEMIC"
    elif _TECH.search(text + " " + email.sender_domain):
        cat = "TECH_OPS"
    elif _CLIENT.search(text):
        cat = "URGENT_CLIENT"
    else:
        cat = "LOW_PRIORITY"
    deadline = extract_deadline(text, email.received)
    needs_reply = cat == "URGENT_CLIENT" and bool(_REPLY_NEEDED.search(text) or deadline)
    first = re.split(r"(?<=[.!?])\s", email.body.strip(), maxsplit=1)[0][:160]
    return Triage(email.id, cat, first, action_item=email.subject if cat in ("URGENT_CLIENT", "ACADEMIC") else None,
                  deadline=deadline, needs_reply=needs_reply, source="rules")
