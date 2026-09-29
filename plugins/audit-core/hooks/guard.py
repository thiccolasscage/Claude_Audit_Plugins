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

# Matched against whole words of the tool name, so "get_assets" is not "set" and
# "list_task_runs" is not "run".
WRITE_VERBS = {
    "create", "update", "delete", "remove", "write", "send", "insert", "upsert", "share",
    "upload", "apply", "execute", "deploy", "trash", "untrash", "move", "publish", "submit",
    "post", "edit", "merge", "rename", "label", "unlabel", "respond", "run", "set", "add",
    "pause", "restore", "reset", "import", "export", "copy", "spawn", "stop", "enable",
    "disable", "invoke", "reply", "comment", "mark", "unmark", "save", "start", "kill",
    "terminate", "use", "duplicate", "generate", "connect", "bind", "revert", "confirm",
    "interact", "unshare",
}
WORD_SPLIT = re.compile(r"[_\-]+|(?<=[a-z])(?=[A-Z])")


def is_write_action(action):
    return any(w.lower() in WRITE_VERBS for w in WORD_SPLIT.split(action))


EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")
# Area code and exchange must start 2-9 (US numbering plan): skips epoch timestamps and IDs.
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})(?!\d)")
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
        if is_write_action(action):
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
