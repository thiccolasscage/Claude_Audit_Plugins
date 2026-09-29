#!/usr/bin/env python3
"""PreToolUse guard. Asks the user before:
  1. any connected-service (MCP) tool that looks like it writes, sends, or deletes
  2. any outbound tool call whose input contains email, phone, or SSN patterns
  3. any call it cannot read or understand (fails safe, never silently allows)
Never prints the identifier itself. Stays silent (allows) otherwise.
Reserved fictional values (example.com emails, 555-0100 to 555-0199 phones) are ignored.
Phone checks cover US-format numbers only.
"""
import json
import re
import sys
import unicodedata
from urllib.parse import unquote

# Strict by default: an MCP tool is allowed without asking only when its name contains a READ verb
# and NO write verb anywhere (so get_and_delete asks). Unknown tools ask. Whole words only, so
# "get_assets" is not "set". Service prefixes (notion-fetch, ha_search) are skipped.
# To stop one harmless tool prompting, add its exact action name to SAFE_ACTIONS.
READ_VERBS = {
    "get", "list", "search", "read", "query", "fetch", "find", "describe", "check", "lookup",
    "analyze", "download", "whoami", "ping", "show", "view", "count", "validate", "resolve", "inspect",
}
SAFE_ACTIONS = {"get_create_automation_instructions", "get_file_upload_url"}
WRITE_VERBS = {
    "create", "update", "delete", "remove", "write", "send", "insert", "upsert", "share",
    "upload", "apply", "execute", "exec", "deploy", "trash", "untrash", "move", "publish", "submit",
    "post", "edit", "merge", "rename", "label", "unlabel", "respond", "run", "set", "add",
    "pause", "restore", "reset", "import", "export", "copy", "spawn", "stop", "enable",
    "disable", "invoke", "reply", "comment", "mark", "unmark", "save", "start", "kill",
    "terminate", "use", "duplicate", "generate", "connect", "bind", "revert", "confirm",
    "interact", "unshare", "call", "trigger", "click", "archive", "clear", "cancel", "rebase",
    "initiate", "remix", "navigate", "detach", "close", "press", "drag", "select",
    "purge", "wipe", "drop", "restart", "shutdown", "replace", "install", "uninstall",
}
WORD_SPLIT = re.compile(r"[_\-]+|(?<=[a-z])(?=[A-Z])")


def is_write_action(action):
    """True unless the name has a read verb and no write verb (unknown tools ask)."""
    if action.lower() in SAFE_ACTIONS:
        return False
    words = [w.lower() for w in WORD_SPLIT.split(action)]
    if any(w in WRITE_VERBS for w in words):
        return True
    return not any(w in READ_VERBS for w in words)


EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")
# Area code and exchange must start 2-9 (US numbering plan): skips epoch timestamps and IDs.
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})(?!\d)")
# Lookarounds instead of \b so an SSN at the start of a line or after a tab is still seen.
SSN = re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")
FAKE_DOMAINS = {"example.com", "example.org", "example.net"}


def flatten(value, out):
    """Collect every string (keys and values) from nested tool input, decoded."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            flatten(k, out)
            flatten(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            flatten(v, out)


def normalize(text):
    """NFKC folds fullwidth characters and non-breaking spaces; unquote undoes %40 style escaping."""
    text = re.sub("[\u2010-\u2015\u2212]", "-", unquote(text))  # fold Unicode dashes so an SSN cannot hide behind one
    return unicodedata.normalize("NFKC", text)


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
        ask("audit-core guard: could not read the tool call, so it cannot be checked. Confirm before proceeding.")
    tool = data.get("tool_name") if isinstance(data, dict) else None
    if not isinstance(tool, str):
        ask("audit-core guard: the tool call has no readable tool name, so it cannot be checked. Confirm before proceeding.")
    strings = []
    flatten(data.get("tool_input", {}), strings)
    payload = normalize("\n".join(strings))
    reasons = []

    if tool.startswith("mcp__"):
        action = tool.split("__")[-1]
        if is_write_action(action):
            service = tool.split("__")[1] if tool.count("__") >= 2 else "a connected service"
            reasons.append(f"{service} tool \"{action}\" is not a recognised read-only action, so it may change something.")

    found = pii_counts(payload)
    if found:
        summary = ", ".join(f"{n} {k}" for k, n in found.items())
        reasons.append(f"The input appears to contain personal identifiers ({summary}) that would leave this session.")

    if reasons:
        ask("audit-core guard: " + " ".join(reasons) + " Confirm before proceeding.")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        ask("audit-core guard: hit an unexpected error while checking this call. Confirm before proceeding.")
