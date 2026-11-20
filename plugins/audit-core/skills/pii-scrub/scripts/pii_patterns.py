"""Identifier patterns shared by the pii-scrub scanner (pii_scan.py) and the guard hook (hooks/guard.py).

Both tools import from here so they cannot drift apart. The file lives inside the skill folder so the
skill still works when its folder is loaded on its own (claude.ai chat and Cowork); the guard reaches it
through the plugin root. Change a pattern here, then run the tests in plugins/audit-core/tests.
"""
import re

# The domain is group 1, so a caller can skip reserved example domains.
EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")

# US format. Area code and exchange must start 2-9 (US numbering plan): skips epoch timestamps and IDs.
# Exchange is group 1 and the last four digits group 2, so a caller can skip 555-0100 to 555-0199.
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})(?!\d)")

# Lookarounds instead of \b so an SSN at the start of a line, after a tab or after a letter is still seen.
# Separators may be a hyphen, dot or space. A hyphen or dot next to it is fine ("SSN-123-45-6789"),
# unless a digit is on its far side ("1-123-45-6789", "123-45-6789-1"): those are longer numbers.
SSN = re.compile(r"(?<!\d)(?<!\d[-.])\d{3}[-. ]\d{2}[-. ]\d{4}(?!\d)(?![-.]\d)")

# Reserved fictional values that are not personal data.
FAKE_DOMAINS = {"example.com", "example.org", "example.net"}


def is_fictional_phone(match):
    """True for a PHONE match in the reserved fictional range 555-0100 to 555-0199."""
    return match.group(1) == "555" and 100 <= int(match.group(2)) <= 199
