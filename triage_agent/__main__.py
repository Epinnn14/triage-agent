"""CLI:  python -m triage_agent [--provider gemini|anthropic|openai|rules] [--source sample|gmail] [--telegram]"""
from __future__ import annotations

import argparse
from datetime import datetime

from .agent import act, briefing, triage_one
from .tools import GmailMailbox, LocalMailbox, Log, TaskList, send_telegram


def main() -> None:
    ap = argparse.ArgumentParser(prog="triage_agent", description="Inbox triage + daily briefing (drafts only, never sends).")
    ap.add_argument("--provider", default="gemini", choices=["gemini", "anthropic", "openai", "rules"])
    ap.add_argument("--source", default="sample", help="'sample' (fixtures/inbox_sample.json), a JSON path, or 'gmail'")
    ap.add_argument("--out", default="out")
    ap.add_argument("--telegram", action="store_true", help="also send the briefing to your Telegram chat")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if a.source == "gmail":
        mailbox = GmailMailbox()
    else:
        mailbox = LocalMailbox("fixtures/inbox_sample.json" if a.source == "sample" else a.source, a.out)
    tasks, log = TaskList(a.out), Log(a.out)

    emails = mailbox.list_unread()
    print(f"→ {len(emails)} unread email(s) · provider={a.provider}\n")
    results = []
    for e in emails:
        t = act(triage_one(e, a.provider), e, mailbox, tasks, log)
        results.append(t)
        flags = f"  flags={t.flags}" if t.flags else ""
        print(f"  [{t.category:<13}] {e.subject[:52]:<52} tools={t.tools}{flags}")
        if a.verbose and t.draft_reply:
            print("      draft:", t.draft_reply.replace("\n", " ")[:140])

    slot = "Morning briefing" if datetime.now().hour < 12 else "Evening digest"
    text = briefing(results, {e.id: e for e in emails}, f"{slot} · {datetime.now():%a %d %b %H:%M}")
    print("\n" + text + "\n")
    if a.telegram:
        print("Telegram:", "sent ✓" if send_telegram(text) else "skipped (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set)")
    print(f"Drafts → {a.out}/drafts/  ·  tasks → {a.out}/tasks.json  ·  log → {a.out}/run_log.jsonl")


if __name__ == "__main__":
    main()
