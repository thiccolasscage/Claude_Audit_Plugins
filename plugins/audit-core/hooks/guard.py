#!/usr/bin/env python3
"""PreToolUse guard. Asks the user before:
  1. any connected-service (MCP) tool that looks like it writes, sends, or deletes
  2. any outbound tool call whose input contains email, phone, or SSN patterns
Never prints the identifier itself. Stays silent (allows) otherwise.
Reserved fictional values (example.com emails, 555-0100 to 555-0199 phones) are ignored.
"""
import json
import re
import sys

WRITE_WORDS = re.compile(
    r"create|update|delete|remove|write|send|insert|upsert|share|upload|apply|execute|"
    r"deploy|trash|move|publish|submit|post|edit|merge|rename|label|respond|run|"
    r"set|add|pause|restore|reset|import|export|copy|spawn|stop|enable|disable|invoke",
    re.I,
)
EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
FAKE_DOMAINS = {"example.com", "example.org", "example.net"}


def pii_counts(text):
    counts = {}
    emails = [m for m in EMAIL.finditer(text) if m.group(1).lower() not in FAKE_DOMAINS]
    phones = [m for m in PHONE.finditer(text)
              if not (m.group(1) == "555" and 100 <= int(m.group(2)) <= 199)]
    ssns = list(SSN.finditer(text))
    if emails: counts["email"] = len(emails)
    if phones: counts["phone"] = len(phones)
    if ssns: counts["SSN pattern"] = len(ssns)
    return counts


def ask(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    payload = json.dumps(data.get("tool_input", {}))
    reasons = []

    if tool.startswith("mcp__"):
        action = tool.split("__")[-1]
        if WRITE_WORDS.search(action):
            service = tool.split("__")[1] if tool.count("__") >= 2 else "a connected service"
            reasons.append(f"This would change something in {service} ({action}).")

    found = pii_counts(payload)
    if found:
        summary = ", ".join(f"{n} {k}" for k, n in found.items())
        reasons.append(f"The input appears to contain personal identifiers ({summary}) that would leave this session.")

    if reasons:
        ask("audit-core guard: " + " ".join(reasons) + " Confirm before proceeding.")
    sys.exit(0)


if __name__ == "__main__":
    main()
