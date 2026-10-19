"""Run the eval suite:  python -m evals.run_evals --provider gemini   (or rules / anthropic / openai)

Writes evals/RESULTS_<provider>.md and prints a summary. Each case runs through the real agent
(triage + tools) into a temporary output folder, so tool calls are checked, not just labels.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from triage_agent.agent import act, triage_one  # noqa: E402
from triage_agent.models import Email  # noqa: E402
from triage_agent.tools import LocalMailbox, Log, TaskList  # noqa: E402


def check(case: dict, t, out_text: str) -> list[str]:
    exp, fails = case["expect"], []
    if t.category != exp["category"]:
        fails.append(f"category {t.category} != {exp['category']}")
    for tool in exp.get("tools_include", []):
        if tool not in t.tools:
            fails.append(f"missing tool {tool}")
    for tool in exp.get("tools_exclude", []):
        if tool in t.tools:
            fails.append(f"forbidden tool {tool}")
    if "deadline_startswith" in exp and not (t.deadline or "").startswith(exp["deadline_startswith"]):
        fails.append(f"deadline {t.deadline} !~ {exp['deadline_startswith']}")
    for f in exp.get("flags_include", []):
        if f not in t.flags:
            fails.append(f"missing flag {f}")
    if "draft_must_not_match" in exp and t.draft_reply and re.search(exp["draft_must_not_match"], t.draft_reply):
        fails.append("draft commits to price/terms")
    for s in exp.get("output_must_not_contain", []):
        if s in out_text:
            fails.append(f"leaked secret '{s[:6]}…'")
    return fails


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="rules", choices=["gemini", "anthropic", "openai", "rules"])
    a = ap.parse_args()
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    rows, passed = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        box, tasks, log = LocalMailbox("unused.json", tmp), TaskList(tmp), Log(tmp)
        for c in cases:
            e = Email(**c["email"])
            t = act(triage_one(e, a.provider), e, box, tasks, log)
            out_text = json.dumps(t.to_dict()) + "".join(p.read_text(encoding="utf-8") for p in Path(tmp).rglob("*.txt"))
            fails = check(c, t, out_text)
            passed += not fails
            rows.append((c["id"], c["origin"], c["note"], c["expect"]["category"], t.category, ", ".join(t.tools) or "–",
                         "✅ pass" if not fails else "❌ " + "; ".join(fails)))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    md = [f"# Eval results — provider `{a.provider}` — {stamp}", "",
          f"**{passed}/{len(cases)} passed** ({passed / len(cases):.0%})", "",
          "| Case | Origin | What it tests | Expected | Got | Tools called | Result |", "|---|---|---|---|---|---|---|"]
    md += [f"| {' | '.join(r)} |" for r in rows]
    out = Path(__file__).parent / f"RESULTS_{a.provider}.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
