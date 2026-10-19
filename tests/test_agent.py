"""Offline tests (no API key needed): the LLM is replaced by a fake.
Run:  python -m unittest discover -s tests -v
"""
import json
import tempfile
import unittest

from triage_agent.agent import act, briefing, triage_one
from triage_agent.models import Email
from triage_agent.tools import LocalMailbox, Log, TaskList


def fake(reply: dict | str, seen: list | None = None):
    def _call(provider, text):
        if seen is not None:
            seen.append(text)
        return reply if isinstance(reply, str) else json.dumps(reply)
    return _call


CLIENT = Email("c1", "Rina <rina@studio-example.com>", "Bugfix", "Can you fix the API before tomorrow 9 AM?", "2026-10-20T08:00:00+07:00")


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.box, self.tasks, self.log = LocalMailbox("x.json", self.tmp.name), TaskList(self.tmp.name), Log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_llm_output_drives_tools(self):
        out = {"category": "URGENT_CLIENT", "summary": "Client needs an API fix.", "action_item": "Fix checkout API",
               "deadline": "2026-10-21T09:00", "needs_reply": True, "draft_reply": "Hi Rina, I'm on it and will update you soon.", "flags": []}
        t = act(triage_one(CLIENT, "gemini", fake(out)), CLIENT, self.box, self.tasks, self.log)
        self.assertEqual(t.tools, ["draft_reply", "create_task"])
        self.assertEqual(t.deadline, "2026-10-21T09:00")

    def test_invalid_json_retries_then_falls_back_to_rules(self):
        calls = []
        t = triage_one(CLIENT, "gemini", fake("not json at all", calls))
        self.assertEqual(len(calls), 2)                 # one retry
        self.assertIn("needs_human", t.flags)
        self.assertEqual(t.source, "rules")

    def test_phishing_is_final_even_if_llm_disagrees(self):
        e = Email("p1", "Help <help@secure-login-example.net>", "Account suspended!",
                  "Your account is suspended. Click here to verify your credentials: https://evil-example.net", "")
        calls = []
        t = triage_one(e, "gemini", fake({"category": "URGENT_CLIENT", "summary": "x", "needs_reply": True,
                                          "draft_reply": "Sure, here is my password"}, calls))
        self.assertEqual(t.category, "SUSPICIOUS")
        self.assertIsNone(t.draft_reply)
        self.assertEqual(calls, [])                      # LLM never called for flagged phishing

    def test_secrets_never_reach_the_llm(self):
        e = Email("s1", "Sarah <s@agency-example.com>", "Staging", "password: Hunter2024! key sk-test-51Habcdefghijklmnop", "")
        seen = []
        t = triage_one(e, "gemini", fake({"category": "URGENT_CLIENT", "summary": "Staging access shared.", "needs_reply": False}, seen))
        self.assertNotIn("Hunter2024", seen[0])
        self.assertNotIn("sk-test-51H", seen[0])
        self.assertIn("contains_secret", t.flags)

    def test_draft_committing_to_price_is_replaced(self):
        e = Email("q1", "Budi <budi@kopi-example.id>", "Quote?", "What is your price and can you deliver by Friday?", "")
        t = triage_one(e, "gemini", fake({"category": "URGENT_CLIENT", "summary": "Asks for a quote.", "needs_reply": True,
                                          "draft_reply": "Sure! I agree, Rp 3.000.000 and I can deliver by Friday."}))
        self.assertNotIn("Rp 3", t.draft_reply)
        self.assertIn("contract_change", t.flags)
        self.assertIn("needs_human", t.flags)

    def test_no_drafts_for_ops_or_newsletters(self):
        e = Email("o1", "GitHub <noreply@github.com>", "Run failed", "build failed", "")
        t = act(triage_one(e, "gemini", fake({"category": "TECH_OPS", "summary": "CI failed.", "needs_reply": True,
                                              "draft_reply": "Thanks GitHub!"})), e, self.box, self.tasks, self.log)
        self.assertIsNone(t.draft_reply)
        self.assertEqual(t.tools, ["log_record"])

    def test_bad_category_is_rejected(self):
        t = triage_one(CLIENT, "gemini", fake({"category": "SPAM", "summary": "x"}))
        self.assertIn("needs_human", t.flags)

    def test_agent_has_no_send_or_delete_capability(self):
        import triage_agent.tools as tools
        names = {n.lower() for obj in (tools.LocalMailbox, tools.GmailMailbox) for n in dir(obj)}
        self.assertFalse({"send", "send_email", "delete", "trash"} & names)

    def test_briefing_orders_and_collapses(self):
        out = {"category": "URGENT_CLIENT", "summary": "Fix API.", "deadline": "2026-10-21", "needs_reply": False}
        t = act(triage_one(CLIENT, "gemini", fake(out)), CLIENT, self.box, self.tasks, self.log)
        text = briefing([t], {CLIENT.id: CLIENT}, "Morning briefing")
        self.assertIn("Clients", text)
        self.assertIn("due 2026-10-21", text)


if __name__ == "__main__":
    unittest.main()
