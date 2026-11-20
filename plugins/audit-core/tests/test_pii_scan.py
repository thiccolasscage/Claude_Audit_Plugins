"""Tests for skills/pii-scrub/scripts/pii_scan.py and the shared pii_patterns.py. Plain unittest.

Run from the repo root:  python -m unittest discover -s plugins/audit-core/tests -v
Only text files are scanned here, so openpyxl, python-docx and python-pptx are not needed.
"""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN / "skills" / "pii-scrub" / "scripts"
SCANNER = SCRIPTS / "pii_scan.py"
GUARD = PLUGIN / "hooks" / "guard.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan = load("pii_scan_under_test", SCANNER)
guard = load("guard_under_test", GUARD)
patterns = sys.modules["pii_patterns"]


def labels(text):
    return [label for label, _ in scan.find(text)]


class SharedPatterns(unittest.TestCase):
    def test_guard_and_scanner_use_the_same_patterns(self):
        by_label = dict(scan.PATTERNS)
        for name in ("EMAIL", "PHONE", "SSN"):
            self.assertIs(by_label[name], getattr(patterns, name), f"scanner {name} is not the shared one")
            self.assertIs(getattr(guard, name), getattr(patterns, name), f"guard {name} is not the shared one")

    def test_guard_asks_when_shared_patterns_are_missing(self):
        # A guard copied away from the plugin can't find pii_patterns.py; it must ask, not crash open.
        with tempfile.TemporaryDirectory() as tmp:
            lone = Path(tmp) / "hooks" / "guard.py"
            lone.parent.mkdir()
            shutil.copy(GUARD, lone)
            proc = subprocess.run([sys.executable, str(lone)], input='{"tool_name": "WebSearch", "tool_input": {}}',
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('"permissionDecision": "ask"', proc.stdout)
        self.assertIn("could not load its shared patterns", proc.stdout)


class Find(unittest.TestCase):
    def test_ssn(self):
        self.assertEqual(labels("SSN 123-45-6789"), ["SSN"])

    def test_ssn_after_a_letter(self):
        # Shared pattern: lookarounds, not \b, so a letter right before it no longer hides it.
        self.assertEqual(labels("ID123-45-6789"), ["SSN"])

    def test_ssn_after_a_hyphen(self):
        self.assertEqual(labels("SSN-123-45-6789"), ["SSN"])

    def test_longer_hyphenated_number_is_not_an_ssn(self):
        self.assertNotIn("SSN", labels("1-123-45-6789"))
        self.assertNotIn("SSN", labels("123-45-6789-1"))

    def test_email(self):
        self.assertEqual(labels("write to jane.doe@corp.org today"), ["EMAIL"])

    def test_phone(self):
        self.assertEqual(labels("call (614) 555-0247"), ["PHONE"])

    def test_phone_with_country_code(self):
        self.assertEqual(labels("+1 614.555.0247"), ["PHONE"])

    def test_bare_ten_digits_starting_with_1_is_a_long_id(self):
        # Not a valid US phone under the shared pattern, but still flagged.
        self.assertEqual(labels("1234567890"), ["LONG_ID_NUMBER"])

    def test_overlap_goes_to_the_earlier_pattern(self):
        hits = scan.find("jane@corp.org")
        self.assertEqual(hits, [("EMAIL", "jane@corp.org")])

    def test_labeled_id(self):
        self.assertIn("LABELED_ID", labels("Student ID 654321"))

    def test_date(self):
        self.assertEqual(labels("born 2010-01-05"), ["DATE"])

    def test_street_address(self):
        self.assertIn("STREET_ADDRESS", labels("lives at 123 Maple St"))

    def test_url(self):
        self.assertEqual(labels("see https://x.io/a"), ["URL"])

    def test_clean_text(self):
        self.assertEqual(scan.find("nothing to see here"), [])


class Mask(unittest.TestCase):
    def test_email_masked(self):
        self.assertEqual(scan.mask("jane.doe@corp.org"), "j***@c***.org")

    def test_number_masked(self):
        self.assertEqual(scan.mask("123-45-6789"), "1********9")

    def test_short_value_fully_masked(self):
        self.assertEqual(scan.mask("abc"), "***")


class CommandLine(unittest.TestCase):
    def run_scanner(self, *paths):
        return subprocess.run([sys.executable, str(SCANNER), *map(str, paths)],
                              capture_output=True, text=True, timeout=20)

    def test_text_file_prints_masked_values_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "notes.txt"
            f.write_text("Reach jane.doe@corp.org or 123-45-6789\n", encoding="utf-8")
            proc = self.run_scanner(f)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("EMAIL: 1", proc.stdout)
        self.assertIn("SSN: 1", proc.stdout)
        self.assertNotIn("jane.doe", proc.stdout)
        self.assertNotIn("123-45-6789", proc.stdout)

    def test_csv_header_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "roster.csv"
            f.write_text("StudentID,First Name\nx,y\n", encoding="utf-8")
            proc = self.run_scanner(f)
        self.assertIn("Identifier-like column headers", proc.stdout)

    def test_missing_file_is_not_scanned(self):
        proc = self.run_scanner(Path(tempfile.gettempdir()) / "no-such-file-audit-core.txt")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("NOT SCANNED", proc.stdout)

    def test_unsupported_format_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "scan.pdf"
            f.write_bytes(b"%PDF-1.4")
            proc = self.run_scanner(f)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("NOT A clean result".upper(), proc.stdout.upper())

    def test_binary_text_file_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "odd.txt"
            f.write_bytes(b"a\x00b\x00")
            proc = self.run_scanner(f)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("NUL bytes", proc.stdout)


if __name__ == "__main__":
    unittest.main()
