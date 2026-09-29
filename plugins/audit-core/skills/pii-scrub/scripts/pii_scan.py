#!/usr/bin/env python3
"""Read-only PII scanner. Reports masked findings; never prints full values.

Usage: python pii_scan.py <file> [<file> ...]
Supports .txt, .md, .csv, .tsv, .xlsx, .docx. Other files are read as text.
Catches structured identifiers only. Names in free text need human review.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

# Ordered by priority: earlier patterns win when matches overlap.
PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("URL", re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    ("DATE", re.compile(
        r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4}\b", re.I)),
    ("STREET_ADDRESS", re.compile(
        r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|"
        r"Ln|Lane|Ct|Court|Way|Pl|Place|Pkwy|Parkway|Cir|Circle)\b\.?")),
    ("ZIP", re.compile(r"\b\d{5}(?:-\d{4})?\b")),
    ("LONG_ID_NUMBER", re.compile(r"\b\d{7,}\b")),
]

HEADER_HINTS = re.compile(
    r"name|first|last|surname|email|e-mail|phone|mobile|cell|fax|address|street|city|zip|postal|"
    r"dob|birth|ssn|social|mrn|medical|record|account|acct|license|patient|student|guardian|"
    r"parent|contact|emergency|ip|url|photo|id\b|_id|number", re.I)


def mask(value: str) -> str:
    v = value.strip()
    if "@" in v:
        user, _, domain = v.partition("@")
        dom, _, tld = domain.rpartition(".")
        return f"{user[:1]}***@{dom[:1]}***.{tld}"
    if len(v) <= 3:
        return "*" * len(v)
    return f"{v[:1]}{'*' * min(len(v) - 2, 8)}{v[-1:]}"


def find(text: str):
    taken = []
    hits = []
    for label, pat in PATTERNS:
        for m in pat.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            taken.append((s, e))
            hits.append((label, m.group()))
    return hits


def cells(path: Path):
    """Yield (location, text, is_header) triples."""
    ext = path.suffix.lower()
    if ext in (".csv", ".tsv"):
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for r, row in enumerate(csv.reader(f, delimiter="\t" if ext == ".tsv" else ",")):
                for c, val in enumerate(row):
                    yield f"row {r + 1}, col {c + 1}", val, r == 0
    elif ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for r, row in enumerate(ws.iter_rows(values_only=True)):
                for c, val in enumerate(row):
                    if val is not None:
                        yield f"{ws.title} row {r + 1}, col {c + 1}", str(val), r == 0
    elif ext == ".docx":
        import docx
        d = docx.Document(path)
        for i, p in enumerate(d.paragraphs):
            yield f"paragraph {i + 1}", p.text, False
        for t, table in enumerate(d.tables):
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    yield f"table {t + 1} row {r + 1}, col {c + 1}", cell.text, r == 0
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                yield f"line {i + 1}", line, False


def scan(path: Path):
    counts = defaultdict(int)
    examples = defaultdict(list)
    headers = []
    for loc, text, is_header in cells(path):
        if is_header and text and HEADER_HINTS.search(text):
            headers.append((loc, text.strip()))
        for label, value in find(text):
            counts[label] += 1
            if len(examples[label]) < 3:
                examples[label].append((loc, mask(value)))
    print(f"\n=== {path.name} ===")
    if headers:
        print("Identifier-like column headers:")
        for loc, h in headers:
            print(f"  {loc}: {h}")
    if not counts:
        print("No structured identifiers matched.")
    for label in sorted(counts, key=lambda k: -counts[k]):
        print(f"{label}: {counts[label]}")
        for loc, m in examples[label]:
            print(f"    e.g. {loc}: {m}")
    print("Not checked by this script: names in free text, rare combinations, small groups.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"Missing: {arg}")
            continue
        scan(p)
