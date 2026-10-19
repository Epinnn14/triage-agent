"""Plain data shapes shared across the agent (stdlib only)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

CATEGORIES = ("URGENT_CLIENT", "ACADEMIC", "TECH_OPS", "LOW_PRIORITY", "SUSPICIOUS")


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    received: str = ""          # ISO timestamp, e.g. 2026-10-19T08:10:00+07:00
    headers: dict = field(default_factory=dict)

    @property
    def sender_domain(self) -> str:
        addr = self.sender.split("<")[-1].rstrip(">").strip().lower()
        return addr.split("@")[-1] if "@" in addr else ""


@dataclass
class Triage:
    email_id: str
    category: str
    summary: str
    action_item: Optional[str] = None
    deadline: Optional[str] = None          # ISO date/datetime or None
    needs_reply: bool = False
    draft_reply: Optional[str] = None
    flags: list = field(default_factory=list)   # e.g. ["contract_change", "contains_secret", "needs_human"]
    tools: list = field(default_factory=list)   # tool calls actually executed, in order
    source: str = "llm"                          # "llm" | "rules" | "guardrail"

    def to_dict(self) -> dict:
        return asdict(self)
