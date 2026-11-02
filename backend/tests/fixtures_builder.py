"""Builds the synthetic test corpus (all formats, incl. a scanned PDF) and the test HR database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE employees (
  employee_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
  region TEXT NOT NULL, join_date TEXT NOT NULL, level TEXT NOT NULL, role TEXT NOT NULL,
  manager_id TEXT REFERENCES employees(employee_id)
);
CREATE TABLE leave_balances (
  employee_id TEXT NOT NULL REFERENCES employees(employee_id), leave_type TEXT NOT NULL,
  balance_days REAL NOT NULL, PRIMARY KEY (employee_id, leave_type)
);
CREATE TABLE leave_requests (
  request_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  leave_type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, working_days INTEGER NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

EMPLOYEES = [
    # id, name, email, phone, region, join, level, role, manager
    ("E100", "Hema Rao", "hema.rao@veltrix.example", "+91 98450 11111", "IN", "2018-01-01", "L6", "hr", None),
    ("E200", "Manoj Iyer", "manoj.iyer@veltrix.example", "+91 98450 22222", "IN", "2017-05-01", "L6", "manager", None),
    ("E201", "Priya Nair", "priya.nair@veltrix.example", "+91 98450 33333", "IN", "2023-01-09", "L3", "employee",
     "E200"),
    ("E202", "Arjun Das", "arjun.das@veltrix.example", "+91 98450 44444", "IN", "2024-03-01", "L2", "employee",
     "E200"),
    ("E300", "Greta Klein", "greta.klein@veltrix.example", "+49 30 1234567", "DE", "2019-02-01", "L5", "manager",
     None),
    ("E301", "Jonas Weber", "jonas.weber@veltrix.example", "+49 30 7654321", "DE", "2022-04-01", "L3", "employee",
     "E300"),
    ("E400", "Sam Carter", "sam.carter@veltrix.example", "+1 512 555 0100", "US", "2021-06-01", "L4", "employee",
     None),
]
BALANCES = {"E100": (15, 10), "E200": (20, 10), "E201": (10, 8), "E202": (2, 8), "E300": (25, 10),
            "E301": (12, 10), "E400": (14, 6)}
REQUESTS = [
    ("req-e201-jul", "E201", "annual", "2026-07-06", "2026-07-10", 5, "approved", "2026-05-01T10:00:00"),
    ("req-e201-aug", "E201", "annual", "2026-08-03", "2026-08-04", 2, "pending", "2026-05-02T10:00:00"),
    ("req-e201-sep", "E201", "annual", "2026-09-01", "2026-09-01", 1, "cancelled", "2026-05-03T10:00:00"),
    ("req-e201-past", "E201", "sick", "2026-06-01", "2026-06-02", 2, "approved", "2026-06-01T08:00:00"),
    ("req-e201-today", "E201", "annual", "2026-06-15", "2026-06-16", 2, "approved", "2026-05-20T08:00:00"),
    ("req-e202-jun", "E202", "sick", "2026-06-22", "2026-06-23", 2, "pending", "2026-06-10T08:00:00"),
    ("req-e301-jul", "E301", "annual", "2026-07-01", "2026-07-03", 3, "pending", "2026-06-01T08:00:00"),
]


def build_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?)", EMPLOYEES)
    for emp, (annual, sick) in BALANCES.items():
        conn.execute("INSERT INTO leave_balances VALUES (?, 'annual', ?)", (emp, annual))
        conn.execute("INSERT INTO leave_balances VALUES (?, 'sick', ?)", (emp, sick))
    conn.executemany("INSERT INTO leave_requests VALUES (?,?,?,?,?,?,?,?)", REQUESTS)
    conn.commit()
    conn.close()


def _meta(doc_id, file, title, doc_type, regions, eff, access="all"):
    return {"doc_id": doc_id, "file": file, "title": title, "doc_type": doc_type, "regions": regions,
            "effective_date": eff, "access_level": access}


META_TABLE_MD = "| Field | Value |\n| --- | --- |\n| Document ID | {id} |\n| Version | 1.0 |\n\n"


def build_corpus(corpus: Path, manifest: Path) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    manifest_items = []

    def md(doc_id, file, title, doc_type, regions, eff, body, access="all"):
        (corpus / file).write_text(f"# {title}\n\n" + META_TABLE_MD.format(id=doc_id) + body, encoding="utf-8")
        manifest_items.append(_meta(doc_id, file, title, doc_type, regions, eff, access))

    md("POL-VOL-V1", "volunteer_v1.md", "Volunteer Policy (Version 1)", "policy", ["GLOBAL"], "2025-01-01",
       "## 1. Volunteer days\n\nEmployees receive 2 volunteer days per year.\n\n"
       "## 2. Sick leave\n\nEmployees receive 10 sick days per year.\n")
    md("FAQ-VOL", "volunteer_faq.md", "Volunteer FAQ", "faq", ["GLOBAL"], "2026-05-01",
       "## How many volunteer days do I get?\n\nYou get 2 volunteer days every year.\n")
    md("ADD-VOL-DE", "volunteer_de.md", "Volunteer Addendum: Germany", "addendum", ["DE"], "2025-06-01",
       "## 1. Volunteer days in Germany\n\nEmployees in Germany receive 5 volunteer days per year.\n")
    md("POL-VOL-V3", "volunteer_v3.md", "Volunteer Policy (Version 3)", "policy", ["GLOBAL"], "2027-01-01",
       "## 1. Volunteer days\n\nFrom 2027 employees receive 4 volunteer days per year.\n")
    md("HB-MGR", "manager_handbook.md", "Manager Handbook", "handbook", ["GLOBAL"], "2026-01-01",
       "## 1. Approvals\n\nManagers approve leave using the MANAGERSECRET process.\n", access="managers")
    md("HR-BANDS", "bands.md", "Salary Bands", "policy", ["GLOBAL"], "2026-01-01",
       "## 1. Bands\n\nThe HRSECRET salary band for L3 is confidential.\n", access="hr")
    md("CAL-DE-2026", "calendar_de.md", "Holiday Calendar 2026: Germany", "calendar", ["DE"], "2026-01-01",
       "## 1. Public holidays 2026\n\n| Date | Day | Holiday |\n| --- | --- | --- |\n"
       "| 25 May 2026 | Monday | Whit Monday |\n| 3 October 2026 | Saturday | German Unity Day |\n")

    # HTML calendar for India, with a restricted-holidays table that must not count.
    (corpus / "calendar_in.html").write_text(
        "<html><head><style>h1{}</style></head><body><nav>Intranet</nav><h1>Holiday Calendar 2026: India</h1>"
        "<table class='meta'><tr><td>Document ID</td><td>CAL-IN-2026</td></tr></table>"
        "<h2>1. Public holidays 2026</h2><table><tr><th>Date</th><th>Day</th><th>Holiday</th></tr>"
        "<tr><td>19 June 2026</td><td>Friday</td><td>Test Festival</td></tr>"
        "<tr><td>15 August 2026</td><td>Saturday</td><td>Independence Day</td></tr></table>"
        "<h2>2. Restricted holidays 2026</h2><p>The office stays open.</p>"
        "<table><tr><th>Date</th><th>Day</th><th>Restricted holiday</th></tr>"
        "<tr><td>17 June 2026</td><td>Wednesday</td><td>Optional Day</td></tr></table>"
        "<footer>footer text</footer></body></html>", encoding="utf-8")
    manifest_items.append(_meta("CAL-IN-2026", "calendar_in.html", "Holiday Calendar 2026: India", "calendar",
                                ["IN"], "2026-01-01"))

    # An older India calendar that must lose to the 2026 one for 2026 dates.
    (corpus / "calendar_in_2025.html").write_text(
        "<html><body><h1>Holiday Calendar 2025: India</h1><h2>Public holidays 2025</h2><table>"
        "<tr><th>Date</th><th>Holiday</th></tr><tr><td>14 January 2025</td><td>Old Festival</td></tr>"
        "</table></body></html>", encoding="utf-8")
    manifest_items.append(_meta("CAL-IN-2025", "calendar_in_2025.html", "Holiday Calendar 2025: India", "calendar",
                                ["IN"], "2025-01-01"))

    # DOCX: version 2 of the policy, with a heading style and a table.
    import docx

    d = docx.Document()
    d.add_heading("Volunteer Policy (Version 2)", level=0)
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Document ID", "POL-VOL-V2"
    t.cell(1, 0).text, t.cell(1, 1).text = "Version", "2.0"
    d.add_heading("1. Volunteer days", level=1)
    d.add_paragraph("Employees receive 3 volunteer days per year.")
    d.add_heading("2. Sick leave", level=1)
    t2 = d.add_table(rows=2, cols=2)
    t2.cell(0, 0).text, t2.cell(0, 1).text = "Topic", "Value"
    t2.cell(1, 0).text, t2.cell(1, 1).text = "Sick days per year", "12 working days"
    d.save(corpus / "volunteer_v2.docx")
    manifest_items.append(_meta("POL-VOL-V2", "volunteer_v2.docx", "Volunteer Policy (Version 2)", "policy",
                                ["GLOBAL"], "2026-04-01"))

    # Text PDF with a bold heading.
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((56, 60), "Travel Policy", fontname="hebo", fontsize=18)
    page.insert_text((56, 100), "1. Hotels", fontname="hebo", fontsize=13)
    page.insert_text((56, 125), "Hotel stays are reimbursed up to 150 EUR per night.", fontname="helv", fontsize=10)
    page.insert_text((56, 140), "Receipts are always required for hotel claims.", fontname="helv", fontsize=10)
    page.insert_text((56, 175), "2. Meals", fontname="hebo", fontsize=13)
    page.insert_text((56, 200), "Meals are covered by the daily allowance.", fontname="helv", fontsize=10)
    pdf.save(corpus / "travel.pdf")
    manifest_items.append(_meta("POL-TRAVEL", "travel.pdf", "Travel Policy", "policy", ["GLOBAL"], "2026-01-01"))

    # Scanned PDF: an image only, no text layer.
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("L", (1700, 700), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 44)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", 44)
        except OSError:
            font = ImageFont.load_default(size=44)
    draw.text((80, 120), "INTERNAL MEMORANDUM", fill=0, font=font)
    draw.text((80, 260), "Employees may work from home up to 3 days per week.", fill=0, font=font)
    img_path = corpus.parent / "scan.png"
    img.save(img_path)
    scan = pymupdf.open()
    sp = scan.new_page(width=595, height=842)
    sp.insert_image(pymupdf.Rect(40, 40, 555, 252), filename=str(img_path))
    scan.save(corpus / "memo_scan.pdf")
    manifest_items.append(_meta("MEMO-SCAN", "memo_scan.pdf", "Memo: Hybrid Work", "memo", ["IN", "US"],
                                "2026-02-01"))

    manifest.write_text(json.dumps(manifest_items, indent=2), encoding="utf-8")
