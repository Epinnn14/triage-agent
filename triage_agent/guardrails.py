"""Hard guardrails enforced in code, not just in the prompt.

1. Secrets are redacted before text reaches the LLM, logs or the briefing.
2. Phishing / credential-bait is caught by rules first and can never get a draft reply.
3. Pricing / contract / timeline commitments are flagged for a human, and any draft that
   commits to them is replaced by a neutral holding reply.
4. There is no code path that sends, deletes or follows links (see tools.py).
"""
from __future__ import annotations

import re

from .models import Email

# --- 1. secret redaction -------------------------------------------------------
_SECRET_PATTERNS = [
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|passcode)\s*[:=]\s*\S+"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)\b(otp|verification code|reset code|kode verifikasi)\s*[:=]?\s*\d{4,8}\b"), r"\1: [REDACTED]"),
    (re.compile(r"\b\d{16}\b"), "[REDACTED_ID_NUMBER]"),  # NIK / card-like numbers
]


def redact(text: str) -> tuple[str, bool]:
    """Return (redacted_text, found_secret)."""
    found = False
    for pattern, repl in _SECRET_PATTERNS:
        text, n = pattern.subn(repl, text)
        found = found or n > 0
    return text, found


# --- 2. phishing / spam rules --------------------------------------------------
_PHISH_WORDS = re.compile(
    r"(?i)(account (is )?(suspended|locked|disabled)|verify (your )?(credentials|account|identity)"
    r"|confirm your password|unusual sign.?in|click (here|below) (to|and) (verify|restore|unlock)"
    r"|update (your )?payment (details|information)|akun anda (diblokir|ditangguhkan))"
)
_URL = re.compile(r"https?://([^/\s\"'>]+)", re.I)
_TRUSTED_TECH = ("github.com", "vercel.com", "netlify.com", "aws.amazon.com", "google.com",
                 "cloudflare.com", "render.com", "railway.app", "digitalocean.com")


def phishing_score(email: Email) -> tuple[int, list[str]]:
    """Cheap, explainable heuristics. >=2 means SUSPICIOUS."""
    reasons, score = [], 0
    text = f"{email.subject}\n{email.body}"
    if _PHISH_WORDS.search(text):
        score += 2
        reasons.append("credential/urgency bait wording")
    links = [h.lower() for h in _URL.findall(email.body)]
    dom = email.sender_domain
    if links and dom and any(dom.split(".")[-2:] != h.split(".")[-2:] for h in links):
        if any(t in dom for t in _TRUSTED_TECH) or _PHISH_WORDS.search(text):
            score += 1
            reasons.append("link domain differs from sender domain")
    if re.search(r"(?i)\b(paypa1|g00gle|micros0ft|app1e)\b", text + dom):
        score += 2
        reasons.append("look-alike brand spelling")
    return score, reasons


# --- 3. contractual / financial commitments -------------------------------------
_CONTRACT = re.compile(
    r"(?i)(rate|price|pricing|budget|quote|invoice amount|discount|contract|agreement|sign|scope"
    r"|extend (the )?deadline|new deadline|timeline|harga|tarif|kontrak)"
)
_COMMIT_IN_DRAFT = re.compile(
    r"(?i)(i agree|we agree|i accept|accepted|deal|confirmed the (rate|price)|i('| wi)ll do it for"
    r"|\$\s?\d|\bidr\b|\brp\s?\d|i can deliver by|i will deliver by|guarantee)"
)

HOLDING_REPLY = (
    "Hi {name},\n\nThanks for your message — I've received it and will review the details "
    "carefully. I'll get back to you personally with a full answer shortly.\n\nBest regards,\nKevin"
)


def mentions_contract(email: Email) -> bool:
    return bool(_CONTRACT.search(f"{email.subject}\n{email.body}"))


def safe_draft(draft: str | None, email: Email) -> tuple[str | None, bool]:
    """If a draft commits to price/timeline/terms, replace it. Returns (draft, replaced)."""
    if not draft:
        return draft, False
    if _COMMIT_IN_DRAFT.search(draft):
        name = email.sender.split("<")[0].strip().split(" ")[0] or "there"
        return HOLDING_REPLY.format(name=name), True
    return draft, False
