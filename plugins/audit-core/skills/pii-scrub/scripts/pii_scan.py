#!/usr/bin/env python3
"""Read-only PII scanner. Reports masked findings; never prints full values.

Usage: python pii_scan.py <file> [<file> ...]
Supports .xlsx, .docx, .pptx and text files (.txt .md .csv .tsv .json .log .html .htm .xml .yaml .yml .rtf).
Any other format, a missing file, a text file holding NUL bytes (binary, or UTF-16 without a BOM),
or a file it cannot read is reported as NOT SCANNED (never as clean) and the script exits with code 2.
An empty text file scans as "No structured identifiers matched".
Catches structured identifiers only. Names in free text need human review.
"""
import codecs
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".html", ".htm", ".xml", ".yaml", ".yml", ".rtf"}
SUPPORTED = TEXT_EXTS | {".xlsx", ".docx", ".pptx"}

# Ordered by priority: earlier patterns win when matches overlap.
PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}[-. ]\d{2}[-. ]\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("URL", re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)),
    ("IP", re.compile(r"(?<!Section )(?<!section )(?<!version )(?<!Version )(?<![vV])\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    # A value after a record-type label, e.g. "MRN: A1234567", "Student ID 654321", "Record # 00123".
    ("LABELED_ID", re.compile(
        r"\b(?:MRN|medical record(?: number| no\.?)?|record (?:#|no\.?|number)|(?:student|employee|patient|"
        r"member|intern|participant|case|client|account|acct)\s*(?:ID|#|no\.?|number))\s*[:#]?\s*[A-Z]{0,4}-?\d[A-Z0-9-]{2,}",
        re.I)),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    ("INTL_PHONE", re.compile(r"(?<![\w+])\+[2-9]\d{0,2}(?=(?:[\s.-]?\d){7,})(?:[\s.-]?\d{2,4}){2,5}(?!\d)")),
    ("DATE", re.compile(
        r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})\b|"
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?,? \d{4}\b|"
        r"\b\d{1,2}(?:st|nd|rd|th)? (?:of )?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,? \d{4}\b",
        re.I)),
    ("STREET_ADDRESS", re.compile(
        r"\b\d{1,6}\s+(?:(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West|NORTH|SOUTH|EAST|WEST)\.?\s+)?"
        r"(?:(?:[A-Z][a-z]+|[A-Z]{2,}|\d+(?:st|nd|rd|th|ST|ND|RD|TH))\s){1,3}"
        r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Way|Pl|Place|Pkwy|Parkway|"
        r"Cir|Circle|Pike|Hwy|Highway|Ter|Terrace|ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|DR|DRIVE|LN|LANE|CT|"
        r"COURT|WAY|PL|PLACE|PKWY|CIR|PIKE|HWY|TER)\b\.?")),
    ("PO_BOX", re.compile(r"\bP\.?\s?O\.?\s?Box\s+\d+", re.I)),
    ("ZIP", re.compile(r"\b\d{5}(?:-\d{4})?\b")),
    # Letter-prefixed IDs like "MR1234567" or "A1234567", and long bare numbers.
    ("PREFIXED_ID", re.compile(r"\b[A-Z]{1,3}\d{6,}\b")),
    ("LONG_ID_NUMBER", re.compile(r"\b\d{7,}\b")),
]

# Whole-word match so "Description" or "Shipping" don't count as identifier headers.
# Headers are split on CamelCase and underscores first, so "StudentID" and "DOB_Date" are caught.
HEADER_HINTS = re.compile(
    r"(?<![a-z])(?:name|first|last|surname|email|e-mail|phone|mobile|cell|fax|address|street|city|zip|"
    r"postal|dob|birth|birthday|age|ssn|social|mrn|medical|record|account|acct|license|patient|student|guardian|"
    r"parent|contact|emergency|ip|url|photo|id|number|participant|intern|employee|member|"
    r"disability|diagnosis|iep|gender|race|ethnicity|counselor|caseworker|host|employer)s?(?![a-z])", re.I)
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[_\-.]+")
HEADER_SCAN_ROWS = 3  # a title row can sit above the real header


def header_index(rows):
    """Index of the header row: the first of the first few rows with 2+ filled cells."""
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        if sum(1 for v in row if v not in (None, "") and str(v).strip()) >= 2:
            return i
    return 0


def looks_like_label(text: str) -> bool:
    """True for short column labels ("First Name", "StudentID"); false for sentences or values."""
    t = text.strip()
    return 0 < len(t) <= 30 and len(t.split()) <= 3 and not re.search(r"[:@\d]", t)


def header_text(text: str) -> str:
    return " ".join(CAMEL.split(text))


ENCODINGS_BY_BOM = [
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
]


def open_text(path: Path):
    """Open a text file, honouring a UTF-8/UTF-16 byte-order mark."""
    with open(path, "rb") as f:
        head = f.read(4)
    enc = next((e for bom, e in ENCODINGS_BY_BOM if head.startswith(bom)), "utf-8")
    return open(path, newline="", encoding=enc, errors="replace")


def looks_binary(path: Path) -> bool:
    """True for a text-extension file that holds NUL bytes without a Unicode BOM (binary, or UTF-16 with no BOM)."""
    with open(path, "rb") as f:
        head = f.read(4)
        if head.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            return True  # UTF-32 is not decoded by this script
        if any(head.startswith(bom) for bom, _ in ENCODINGS_BY_BOM):
            return False
        f.seek(0)
        while chunk := f.read(1 << 20):
            if b"\x00" in chunk:
                return True
    return False


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
        with open_text(path) as f:
            rows = list(csv.reader(f, delimiter="\t" if ext == ".tsv" else ","))
        h = header_index(rows)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                yield f"row {r + 1}, col {c + 1}", val, r == h
    elif ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        for sn, ws in enumerate(wb.worksheets, start=1):
            rows = ws.iter_rows(values_only=True)
            head = [next(rows, ()) for _ in range(HEADER_SCAN_ROWS)]
            h = header_index(head)
            import itertools
            for r, row in enumerate(itertools.chain(head, rows)):
                for c, val in enumerate(row or ()):
                    if val is not None:
                        yield f"sheet {sn} row {r + 1}, col {c + 1}", str(val), r == h
    elif ext == ".docx":
        import docx
        d = docx.Document(path)
        for i, p in enumerate(d.paragraphs):
            yield f"paragraph {i + 1}", p.text, False
        for t, table in enumerate(d.tables):
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    yield f"table {t + 1} row {r + 1}, col {c + 1}", cell.text, r == 0
        for s, section in enumerate(d.sections):
            for kind, part in (("header", section.header), ("footer", section.footer),
                               ("first-page header", section.first_page_header),
                               ("first-page footer", section.first_page_footer),
                               ("even-page header", section.even_page_header),
                               ("even-page footer", section.even_page_footer)):
                if part.is_linked_to_previous:
                    continue
                for i, p in enumerate(part.paragraphs):
                    yield f"section {s + 1} {kind} paragraph {i + 1}", p.text, False
                for t, table in enumerate(part.tables):
                    for r, row in enumerate(table.rows):
                        for c, cell in enumerate(row.cells):
                            yield f"section {s + 1} {kind} table {t + 1} row {r + 1}, col {c + 1}", cell.text, False
    elif ext == ".pptx":
        from pptx import Presentation
        prs = Presentation(path)

        def shape_text(shapes, where):
            for shape in shapes:
                descr = shape._element.xpath("./*[1]/p:cNvPr/@descr")
                if descr:
                    yield f"{where} shape {shape.shape_id} alt text", descr[0], False
                if shape.shape_type == 6:  # group
                    yield from shape_text(shape.shapes, where)
                    continue
                if shape.has_text_frame:
                    for i, p in enumerate(shape.text_frame.paragraphs):
                        yield f"{where} shape {shape.shape_id} paragraph {i + 1}", "".join(r.text for r in p.runs), False
                if getattr(shape, "has_table", False) and shape.has_table:
                    for r, row in enumerate(shape.table.rows):
                        for c, cell in enumerate(row.cells):
                            yield f"{where} table row {r + 1}, col {c + 1}", cell.text, r == 0

        for n, slide in enumerate(prs.slides, start=1):
            yield from shape_text(slide.shapes, f"slide {n}")
            tf = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
            if tf is not None:
                for i, p in enumerate(tf.paragraphs):
                    yield f"slide {n} speaker notes paragraph {i + 1}", "".join(r.text for r in p.runs), False
    else:
        with open_text(path) as f:
            for i, line in enumerate(f):
                yield f"line {i + 1}", line, False


def properties(path: Path):
    """Yield (location, value) for author-type document properties, which hold real names."""
    ext = path.suffix.lower()
    if ext == ".docx":
        import docx
        cp = docx.Document(path).core_properties
        pairs = [("author", cp.author), ("last modified by", cp.last_modified_by)]
    elif ext == ".pptx":
        from pptx import Presentation
        cp = Presentation(path).core_properties
        pairs = [("author", cp.author), ("last modified by", cp.last_modified_by)]
    elif ext == ".xlsx":
        from openpyxl import load_workbook
        props = load_workbook(path, read_only=True).properties
        pairs = [("creator", props.creator), ("last modified by", props.lastModifiedBy)]
    else:
        return
    for name, value in pairs:
        if value and str(value).strip():
            yield f"document property '{name}'", str(value)


UNSCANNED_NOTE = {
    ".docx": "Not scanned: comments, footnotes, text boxes. Check these by hand.",
    ".xlsx": "Not scanned: cell comments, hidden names. Check these by hand.",
    ".pptx": "Not scanned: comments, chart data, embedded workbooks, images and photos. Check these by hand.",
}


def scan(path: Path):
    counts = defaultdict(int)
    examples = defaultdict(list)
    headers = []
    for loc, text, is_header in cells(path):
        hits = find(text)
        if is_header and text and HEADER_HINTS.search(header_text(text)):
            # A "header" that itself holds an identifier is really data (headerless file): mask it.
            headers.append((loc, text.strip() if looks_like_label(text) and not hits else mask(text) + " (may be data, masked)"))
        for label, value in hits:
            counts[label] += 1
            if len(examples[label]) < 3:
                examples[label].append((loc, mask(value)))
    for loc, value in properties(path):
        counts["AUTHOR_PROPERTY"] += 1
        if len(examples["AUTHOR_PROPERTY"]) < 3:
            examples["AUTHOR_PROPERTY"].append((loc, mask(value)))
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
    if path.suffix.lower() in UNSCANNED_NOTE:
        print(UNSCANNED_NOTE[path.suffix.lower()])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    unscanned = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"\nNOT SCANNED: {p.name} (file not found)")
            unscanned += 1
        elif p.suffix.lower() not in SUPPORTED:
            print(f"\nNOT SCANNED: {p.name} (unsupported format {p.suffix or 'with no extension'}; "
                  "convert to .txt, .csv, .docx, .xlsx or .pptx first. This is NOT a clean result.)")
            unscanned += 1
        elif p.suffix.lower() in TEXT_EXTS and looks_binary(p):
            print(f"\nNOT SCANNED: {p.name} (contains NUL bytes: binary, or UTF-16 without a byte-order mark; "
                  "re-save as UTF-8 text. This is NOT a clean result.)")
            unscanned += 1
        else:
            try:
                scan(p)
            except ImportError as e:
                print(f"\nNOT SCANNED: {p.name} (missing Python library '{e.name}'; pip install it and rerun)")
                unscanned += 1
            except Exception as e:
                print(f"\nNOT SCANNED: {p.name} ({type(e).__name__} while reading)")
                unscanned += 1
    sys.exit(2 if unscanned else 0)
