"""Tests for hooks/guard.py. Plain unittest, no extra installs.

Run from the repo root:  python -m unittest discover -s plugins/audit-core/tests -v
The guard is run as a subprocess with the tool call on stdin, the same way the hook runs it.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "hooks" / "guard.py"


def run_guard(payload):
    """Return (exit code, parsed JSON or None) for one tool call."""
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    # Send UTF-8 bytes, as the hook receives them, so the test can't agree with a wrong locale decode.
    proc = subprocess.run([sys.executable, str(GUARD)], input=raw.encode("utf-8"), capture_output=True, timeout=10)
    out = proc.stdout.decode("utf-8").strip()
    return proc.returncode, (json.loads(out) if out else None)


def reason(result):
    return result["hookSpecificOutput"]["permissionDecisionReason"]


class GuardBugRepro(unittest.TestCase):
    def test_read_query_with_sql_write_names_the_query(self):
        # Before the fix, `service` was only set in the write branch, so this crashed and
        # the guard fell back to its generic "unexpected error" ask.
        code, result = run_guard({"tool_name": "mcp__db__read_query", "tool_input": {"sql": "DELETE FROM t"}})
        self.assertEqual(code, 0)
        self.assertIsNotNone(result)
        self.assertIn("query looks like it changes data", reason(result))
        self.assertIn("db", reason(result))
        self.assertNotIn("unexpected error", reason(result))

    def test_short_tool_name_with_sql_write(self):
        code, result = run_guard({"tool_name": "mcp__query", "tool_input": {"sql": "DROP TABLE t"}})
        self.assertEqual(code, 0)
        self.assertIn("connected service query looks like it changes data", reason(result))


class GuardDecisions(unittest.TestCase):
    def assertSilent(self, payload):
        code, result = run_guard(payload)
        self.assertEqual(code, 0)
        self.assertIsNone(result, f"expected no prompt, got {result}")

    def assertAsks(self, payload, *phrases):
        code, result = run_guard(payload)
        self.assertEqual(code, 0)
        self.assertIsNotNone(result, "expected a prompt, got silence")
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "ask")
        for p in phrases:
            self.assertIn(p, reason(result))
        return result

    def test_read_only_tool_is_silent(self):
        self.assertSilent({"tool_name": "mcp__notion__search", "tool_input": {"query": "meeting notes"}})

    def test_read_query_with_select_is_silent(self):
        self.assertSilent({"tool_name": "mcp__db__read_query", "tool_input": {"sql": "SELECT * FROM t"}})

    def test_write_tool_asks(self):
        self.assertAsks({"tool_name": "mcp__notion__create_page", "tool_input": {}},
                        "notion tool \"create_page\" is not a recognised read-only action")

    def test_read_and_write_verbs_ask(self):
        self.assertAsks({"tool_name": "mcp__x__get_and_delete", "tool_input": {}}, "get_and_delete")

    def test_unknown_tool_asks(self):
        self.assertAsks({"tool_name": "mcp__x__frobnicate", "tool_input": {}}, "frobnicate")

    def test_safe_action_is_silent(self):
        self.assertSilent({"tool_name": "mcp__ha__get_create_automation_instructions", "tool_input": {}})

    def test_get_assets_is_not_set(self):
        self.assertSilent({"tool_name": "mcp__x__get_assets", "tool_input": {}})

    def test_camel_case_write_verb_asks(self):
        self.assertAsks({"tool_name": "mcp__x__deletePage", "tool_input": {}}, "deletePage")

    def test_web_search_plain_is_silent(self):
        self.assertSilent({"tool_name": "WebSearch", "tool_input": {"query": "python unittest docs"}})

    def test_email_asks_and_is_not_echoed(self):
        result = self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "jane.doe@corp.org"}}, "email")
        self.assertNotIn("jane.doe", reason(result))

    def test_example_domain_email_is_silent(self):
        self.assertSilent({"tool_name": "WebSearch", "tool_input": {"query": "test@example.com"}})

    def test_url_encoded_email_asks(self):
        self.assertAsks({"tool_name": "WebFetch", "tool_input": {"url": "https://x.io/?u=jane%40corp.org"}}, "email")

    def test_phone_asks(self):
        self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "call (614) 555-0247"}}, "phone")

    def test_fictional_555_phone_is_silent(self):
        self.assertSilent({"tool_name": "WebSearch", "tool_input": {"query": "call 513-555-0123"}})

    def test_epoch_timestamp_is_not_a_phone(self):
        self.assertSilent({"tool_name": "WebSearch", "tool_input": {"query": "ts 1730000000"}})

    def test_ssn_asks(self):
        self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "123-45-6789"}}, "SSN pattern")

    def test_ssn_after_a_hyphen_asks(self):
        self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "SSN-123-45-6789"}}, "SSN pattern")

    def test_ssn_behind_unicode_dash_asks(self):
        self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "123–45–6789"}}, "SSN pattern")

    def test_labeled_id_asks(self):
        self.assertAsks({"tool_name": "Artifact", "tool_input": {"content": "MRN: A12345"}}, "labeled ID")

    def test_birth_date_label_asks(self):
        self.assertAsks({"tool_name": "Artifact", "tool_input": {"content": "DOB Jan 5 2010"}}, "labeled ID")

    def test_label_as_field_name_asks(self):
        self.assertAsks({"tool_name": "ArtifactData", "tool_input": {"data": {"student ID": 445566}}}, "labeled ID")

    def test_one_ssn_is_counted_once(self):
        # flatten() used to add each value on its own and again as "key: value", so this said "2 SSN pattern".
        result = self.assertAsks({"tool_name": "WebSearch", "tool_input": {"query": "123-45-6789"}}, "(1 SSN pattern)")
        self.assertNotIn("2 SSN", reason(result))

    def test_matches_are_counted_once_each(self):
        self.assertAsks({"tool_name": "Artifact", "tool_input": {
            "content": "jane.doe@corp.org", "notes": ["sam.roe@corp.org", {"to": "123-45-6789"}]}},
            "(2 email, 1 SSN pattern)")

    def test_email_in_a_field_name_is_counted_once(self):
        self.assertAsks({"tool_name": "ArtifactData", "tool_input": {"data": {"jane.doe@corp.org": "yes"}}}, "(1 email)")

    def test_labeled_id_as_field_name_is_counted_once(self):
        self.assertAsks({"tool_name": "ArtifactData", "tool_input": {"data": {"MRN": "A12345"}}},
                        "(1 labeled ID or birth date)")

    def test_phone_split_across_key_and_value_asks(self):
        self.assertAsks({"tool_name": "ArtifactData", "tool_input": {"data": {"phone 614": "555-0247"}}}, "(1 phone)")

    def test_unreadable_input_asks(self):
        self.assertAsks("not json", "could not read the tool call")

    def test_missing_tool_name_asks(self):
        self.assertAsks({"tool_input": {}}, "no readable tool name")


if __name__ == "__main__":
    unittest.main()
