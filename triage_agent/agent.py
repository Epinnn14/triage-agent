"""The agent loop: fetch → redact → security pre-check → LLM (validated, 1 retry) → guardrails → tools → briefing."""
from __future__ import annotations

from typing import Callable

from . import guardrails, rules
from .llm import LLMError, build_user_text, call_llm, parse_and_validate
from .models import Email, Triage

PRIORITY = {"URGENT_CLIENT": "high", "ACADEMIC": "medium", "TECH_OPS": "low", "LOW_PRIORITY": "none", "SUSPICIOUS": "alert"}


def triage_one(email: Email, provider: str, llm: Callable[[str, str], str] | None = None) -> Triage:
    """Decide what an email is. Pure function except for the LLM call (injectable for tests)."""
    body, had_secret = guardrails.redact(email.body)
    pre = rules.classify(email)

    # Guardrail: rules-flagged phishing is final; the LLM never sees a chance to draft a reply.
    if pre.category == "SUSPICIOUS":
        pre.source = "guardrail"
        pre.flags = sorted(set(pre.flags) | ({"contains_secret"} if had_secret else set()))
        return pre

    if provider == "rules":
        t = pre
    else:
        call = llm or (lambda p, text: call_llm(p, text))
        t, last_err = None, None
        for _ in range(2):  # one retry on invalid output
            try:
                data = parse_and_validate(call(provider, build_user_text(email, body)))
                t = Triage(email.id, data["category"], data["summary"], data.get("action_item"), data["deadline"],
                           data["needs_reply"], data.get("draft_reply"), list(data["flags"]), source="llm")
                break
            except (LLMError, KeyError, IndexError, OSError) as e:  # network or schema problems
                last_err = e
        if t is None:
            t = pre
            t.flags.append("needs_human")
            t.summary = f"[LLM failed: {str(last_err)[:80]}] " + t.summary

    # --- post-guardrails (apply to LLM *and* rules output) ---
    if had_secret and "contains_secret" not in t.flags:
        t.flags.append("contains_secret")
    if t.summary:
        t.summary, _ = guardrails.redact(t.summary)
    if guardrails.mentions_contract(email) and t.category == "URGENT_CLIENT" and "contract_change" not in t.flags:
        t.flags.append("contract_change")
    if t.category not in ("URGENT_CLIENT", "ACADEMIC"):
        t.needs_reply, t.draft_reply = False, None
    if t.needs_reply and not t.draft_reply:
        name = email.sender.split("<")[0].strip().split(" ")[0] or "there"
        t.draft_reply = guardrails.HOLDING_REPLY.format(name=name)
    if t.draft_reply:
        t.draft_reply, replaced = guardrails.safe_draft(t.draft_reply, email)
        t.draft_reply, _ = guardrails.redact(t.draft_reply)
        if replaced and "needs_human" not in t.flags:
            t.flags.append("needs_human")
    return t


def act(t: Triage, email: Email, mailbox, tasks, log) -> Triage:
    """Execute the allowed tools for a decision. Records every call in t.tools and the run log."""
    if t.category == "SUSPICIOUS":
        t.tools.append("flag_security_alert")
    elif t.category == "LOW_PRIORITY":
        t.tools.append("archive_or_skip")
    elif t.category == "TECH_OPS":
        t.tools.append("log_record")
    else:
        if t.needs_reply and t.draft_reply:
            mailbox.create_draft(email, t.draft_reply)
            t.tools.append("draft_reply")
        if t.action_item or t.deadline:
            tasks.create_task(f"[{t.category}] {t.action_item or email.subject}", t.deadline, PRIORITY[t.category])
            t.tools.append("create_task")
    log.record({"email_id": email.id, "category": t.category, "tools": t.tools, "flags": t.flags, "source": t.source})
    return t


def briefing(results: list[Triage], emails: dict[str, Email], title: str) -> str:
    """Markdown daily briefing. Urgent first; receipts and newsletters collapsed to counts."""
    by = {c: [r for r in results if r.category == c] for c in PRIORITY}
    lines = [f"*{title}*", ""]
    if by["SUSPICIOUS"]:
        lines.append(f"🚩 *Security* — {len(by['SUSPICIOUS'])} suspicious message(s). Don't click links.")
        for r in by["SUSPICIOUS"]:
            lines.append(f"  • {emails[r.email_id].subject[:70]}")
        lines.append("")
    for cat, label in (("URGENT_CLIENT", "🔴 *Clients*"), ("ACADEMIC", "🎓 *Academic*")):
        if by[cat]:
            lines.append(label)
            for r in sorted(by[cat], key=lambda x: x.deadline or "9999"):
                due = f" — due {r.deadline}" if r.deadline else ""
                extra = " (draft ready)" if "draft_reply" in r.tools else ""
                warn = " ⚠️ needs your decision" if {"contract_change", "needs_human"} & set(r.flags) else ""
                lines.append(f"  • {r.summary}{due}{extra}{warn}")
            lines.append("")
    if by["TECH_OPS"]:
        lines.append(f"⚙️ Tech ops: {len(by['TECH_OPS'])} logged (no action needed unless listed above).")
    if by["LOW_PRIORITY"]:
        lines.append(f"📨 Skipped {len(by['LOW_PRIORITY'])} newsletter/promo email(s) → weekly reading list.")
    return "\n".join(lines).strip()
