"""LLM step: one call per email, strict JSON out, validated before anything uses it.

Providers (stdlib HTTP only, no SDKs):
  gemini     GEMINI_API_KEY     free tier key from Google AI Studio
  anthropic  ANTHROPIC_API_KEY
  openai     OPENAI_API_KEY
Model is set with TRIAGE_MODEL (defaults below). If your provider has retired a default
model, set TRIAGE_MODEL to a current one.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .models import CATEGORIES, Email

DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "anthropic": "claude-sonnet-4-5", "openai": "gpt-4o-mini"}

SYSTEM_PROMPT = """You are 'TriageAgent', an inbound communication triage assistant for a software engineering
student and freelance developer (Kevin, Jakarta, UTC+7).

For the ONE email you are given, return ONLY a JSON object (no prose, no code fences) with:
{
  "category": one of ["URGENT_CLIENT","ACADEMIC","TECH_OPS","LOW_PRIORITY","SUSPICIOUS"],
  "summary": "<= 2 sentences, plain words",
  "action_item": "what Kevin must do, or null",
  "deadline": "ISO date or datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM) resolved against the received time, or null",
  "needs_reply": true/false,
  "draft_reply": "short, professional, courteous reply text, or null",
  "flags": [zero or more of "contract_change", "contains_secret", "needs_human"]
}

Rules:
- URGENT_CLIENT: client inquiries, paid work, client deadlines, milestone feedback.
- ACADEMIC: university / course / exam / submission notices.
- TECH_OPS: GitHub, hosting, cloud billing receipts, build or uptime alerts.
- LOW_PRIORITY: newsletters, promotions, marketing digests.
- SUSPICIOUS: phishing, credential requests, fake account warnings. Never draft a reply for these.
- Draft a reply ONLY when needs_reply is true and category is URGENT_CLIENT (or ACADEMIC when a reply is explicitly requested).
- Never agree to prices, rates, contracts, scope changes or delivery dates in a draft. If the email asks about
  them, add flag "contract_change" and draft a neutral acknowledgement that Kevin will reply personally.
- Never include links, passwords, tokens or codes in your output.
- You cannot send email. Drafts are reviewed by Kevin.
"""


class LLMError(RuntimeError):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed provider URLs only)
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # surface the provider's reason (e.g. model not found, bad key)
        detail = e.read().decode("utf-8", "ignore")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except (ValueError, AttributeError):
            pass
        raise LLMError(f"HTTP {e.code}: {str(detail)[:160]}") from None


def call_llm(provider: str, user_text: str, model: str | None = None) -> str:
    model = model or os.environ.get("TRIAGE_MODEL") or DEFAULT_MODELS[provider]
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        out = _post(url, {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }, {"x-goog-api-key": _key("GEMINI_API_KEY")})
        return out["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "anthropic":
        out = _post("https://api.anthropic.com/v1/messages", {
            "model": model, "max_tokens": 800, "temperature": 0, "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_text}],
        }, {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in out["content"])
    if provider == "openai":
        out = _post("https://api.openai.com/v1/chat/completions", {
            "model": model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}],
        }, {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}"})
        return out["choices"][0]["message"]["content"]
    raise LLMError(f"unknown provider {provider!r}")


def list_gemini_models() -> list[str]:
    """Models your Gemini key can call with generateContent."""
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                 headers={"x-goog-api-key": _key("GEMINI_API_KEY")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            models = json.loads(r.read().decode()).get("models", [])
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}") from None
    return [m["name"].split("/", 1)[-1] for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]


def _key(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise LLMError(f"{name} is not set (see README → Setup)")
    return v


def build_user_text(email: Email, body: str) -> str:
    return (f"Received: {email.received}\nFrom: {email.sender}\nSubject: {email.subject}\n\n"
            f"{body[:6000]}")


def parse_and_validate(raw: str) -> dict:
    """Strict schema check. Raises LLMError with a reason on any violation."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"not JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("not an object")
    if data.get("category") not in CATEGORIES:
        raise LLMError(f"bad category {data.get('category')!r}")
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise LLMError("missing summary")
    if data.get("deadline") not in (None, "") and not re.fullmatch(r"20\d\d-\d\d-\d\d(T\d\d:\d\d(:\d\d)?)?", str(data["deadline"])):
        raise LLMError(f"bad deadline {data.get('deadline')!r}")
    data["deadline"] = data.get("deadline") or None
    data["needs_reply"] = bool(data.get("needs_reply"))
    data["flags"] = [f for f in (data.get("flags") or []) if f in ("contract_change", "contains_secret", "needs_human")]
    for k in ("action_item", "draft_reply"):
        if data.get(k) is not None and not isinstance(data[k], str):
            raise LLMError(f"{k} must be string or null")
    return data
