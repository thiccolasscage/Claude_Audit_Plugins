# personal-plugins

Claude plugin marketplace. This repo is public, so it contains rules and agent definitions only. Never commit data, answer keys, or anything with real names or contact details; .gitignore blocks common data files as a backstop.

## audit-core

| Component | What it does | Works in |
| --- | --- | --- |
| independent-audit skill | Staged review: scope, review, skeptic pass, evidence based report, user decides | Chat, Cowork, Claude Code |
| pii-scrub skill | Scan, masked report, confirm plan, scrub to new file, verify | Chat, Cowork, Claude Code |
| skeptic agent | Tries to refute every finding against the source | Cowork, Claude Code |
| privacy-auditor agent | Identifiers, over collection, small group risk | Cowork, Claude Code |
| guard hook | Asks before connected-service writes or sending personal identifiers | Cowork, Claude Code (needs Python 3 as `python3`, `python` or `py`; asks if none works) |

The guard is strict: it allows a connected-service tool without asking only when the name contains a read verb (`get`, `list`, `search`, `read`, ...) and no write verb anywhere (`get_and_delete` asks). Unknown or write-style tools ask, and so does any call it cannot read. To stop one harmless tool prompting, add its exact action name to `SAFE_ACTIONS` in `plugins/audit-core/hooks/guard.py`. Emails, US phone numbers and SSN patterns in any outbound call also ask (obfuscated forms like "bob at corp dot org" or unformatted nine-digit numbers are not caught).

## Install

1. Push this folder to a GitHub repo. This one is public; keep every data file out of it.
2. claude.ai: Customize > Plugins > Add > Add marketplace > Add from a repository > enter owner/repo.
3. Install audit-core from that marketplace.
4. Claude Code picks it up at next session start when signed in with the same account (v2.1.273 or later).

## Updating

Edit, bump the version in plugins/audit-core/.claude-plugin/plugin.json, push, then click Update on the marketplace in Customize > Plugins. Claude.ai does not pull changes on its own.

Agent descriptions that contain examples must be valid YAML. Use either a folded block (`description: >`) or a single quoted line with `
` for line breaks (the current style, which the desktop app accepts). A plain multi-line description with `Context:` lines is invalid YAML, and the `tools:` limit is then silently ignored, leaving the agent with every tool. After any edit, parse the header and check that `tools` reads as a list.

## Testing auditors

Keep seeded-error test sets and their answer keys outside this repo. Score findings with a script the reviewers cannot read.
