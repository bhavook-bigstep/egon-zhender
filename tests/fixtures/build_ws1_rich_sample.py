"""Generate a RICH synthetic WS-1 sample for the PoC capability demo.

Everything here is **synthetic** — generated with Faker (MIT) using a fixed seed, so it is
reproducible (Contract 4) and contains no real person's data (privacy rules). It exercises
the full pipeline against the real engines:

  * real document formats — .txt, born-digital .pdf (reportlab), scanned .png (Pillow, for
    OCR), .docx, .xlsx — so extraction + the OCR gate actually engage (docling handles all);
  * well-formed fake PII that Presidio detects — credit card (Luhn), IBAN, SSN, passport,
    driver licence — mapped to the approved taxonomy (financial / government_id);
  * financial / health context prose for the semantic screen to route.

This is demo seed data used until the input source is connected to Databricks. Run from the
repo root:  python tests/fixtures/build_ws1_rich_sample.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx import Document
from faker import Faker
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

FIXTURES = Path("tests/fixtures")
SAMPLE_DIR = FIXTURES / "ws1_sample_rich"
MANIFEST_PATH = FIXTURES / "ws1_rich_manifest.json"

fake = Faker("en_US")
Faker.seed(1729)  # deterministic content -> stable hashes -> stable run_id (Contract 4)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _png_with_text(lines: list[str]) -> bytes:
    """Render text onto a white PNG so the OCR gate must engage (docling OCRs it)."""
    font = _font(30)
    img = Image.new("RGB", (1000, 60 + 46 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((40, 30 + 46 * i), line, fill="black", font=font)
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf(title: str, lines: list[str]) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(72, 720, title)
    pdf.setFont("Helvetica", 12)
    y = 690
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 22
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _docx(title: str, lines: list[str]) -> bytes:
    from io import BytesIO

    doc = Document()
    doc.add_heading(title, level=1)
    for line in lines:
        doc.add_paragraph(line)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _xlsx(header: list[str], rows: list[list[str]]) -> bytes:
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    ws.title = "accounts"
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []

    def add(source_id: str, filename: str, content_type: str, data: bytes, project: str) -> None:
        (SAMPLE_DIR / filename).write_bytes(data)
        manifest.append(
            {
                "source_id": source_id,
                "content_type": content_type,
                "content_hash": hashlib.sha256(data).hexdigest(),
                "path": filename,
                "author": fake.name(),
                "datetime": "2026-02-01T10:00:00Z",
                "linked_executive": f"exec-{fake.random_int(100, 999)}",
                "linked_project": project,
            }
        )

    # 1. Financial note (text) — credit card (Luhn) + IBAN + salary context.
    add(
        "note_fin_001",
        "note_fin_001.txt",
        "text/plain",
        (
            "Prince Houston file note\n"
            f"Client {fake.name()} onboarding review.\n"
            f"Corporate card on file: {fake.credit_card_number()}.\n"
            f"Settlement account IBAN {fake.iban()}.\n"
            f"Agreed annual salary package GBP {fake.random_int(90, 250)},000 plus bonus.\n"
        ).encode(),
        "proj-alpha",
    )

    # 2. Government-ID note (text) — SSN + passport + driver licence.
    add(
        "note_gov_001",
        "note_gov_001.txt",
        "text/plain",
        (
            "Prince Houston file note\n"
            f"Identity verification for {fake.name()}.\n"
            f"SSN {fake.ssn()} confirmed against records.\n"
            f"Passport No: {fake.random_int(100000000, 999999999)}.\n"
            f"Driver licence {fake.bothify('?#######').upper()}.\n"
        ).encode(),
        "proj-alpha",
    )

    # 3. Financial statement (born-digital PDF).
    add(
        "statement_fin_001",
        "statement_fin_001.pdf",
        "application/pdf",
        _pdf(
            "Confidential Account Statement",
            [
                f"Account holder: {fake.name()}",
                f"Card number: {fake.credit_card_number()}",
                f"IBAN: {fake.iban()}",
                f"Closing balance: GBP {fake.random_int(10, 900)},{fake.random_int(100, 999)}",
                "Compensation and bonus schedule attached.",
            ],
        ),
        "proj-beta",
    )

    # 4. Clinical memo (born-digital PDF) — health context for the semantic screen.
    add(
        "memo_health_001",
        "memo_health_001.pdf",
        "application/pdf",
        _pdf(
            "Occupational Health Memo",
            [
                f"Patient: {fake.name()}",
                f"Medical record number: MRN-{fake.random_int(100000, 999999)}",
                "Diagnosis: hypertension; ongoing clinical review of the condition.",
                "Treatment plan and medication dosage under specialist supervision.",
            ],
        ),
        "proj-beta",
    )

    # 5. Scanned ID card (PNG, no text layer) — forces OCR; government_id content.
    add(
        "scan_gov_001",
        "scan_gov_001.png",
        "image/png",
        _png_with_text(
            [
                "IDENTITY VERIFICATION RECORD",
                f"Name: {fake.name()}",
                f"SSN: {fake.ssn()}",
                f"Passport: {fake.random_int(100000000, 999999999)}",
            ]
        ),
        "proj-beta",
    )

    # 6. Compensation letter (DOCX) — financial context.
    add(
        "letter_comp_001",
        "letter_comp_001.docx",
        _DOCX_MIME,
        _docx(
            "Private & Confidential — Compensation",
            [
                f"Dear {fake.name()},",
                f"Your revised base salary is GBP {fake.random_int(120, 300)},000.",
                f"A discretionary bonus and equity award apply. Card on file "
                f"{fake.credit_card_number()}.",
            ],
        ),
        "proj-gamma",
    )

    # 7. Account register (XLSX) — table of financial identifiers.
    add(
        "accounts_001",
        "accounts_001.xlsx",
        _XLSX_MIME,
        _xlsx(
            ["Name", "IBAN", "Card"],
            [[fake.name(), fake.iban(), fake.credit_card_number()] for _ in range(5)],
        ),
        "proj-gamma",
    )

    # 8. Benign note (text) — no PII -> not_flagged (true negative).
    add(
        "note_clean_001",
        "note_clean_001.txt",
        "text/plain",
        (
            b"Prince Houston file note\n"
            b"Quarterly team sync completed. Roadmap and general availability discussed.\n"
            b"No client-specific or sensitive details recorded. No further actions.\n"
        ),
        "proj-gamma",
    )

    manifest.sort(key=lambda record: record["source_id"])
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest)} items to {SAMPLE_DIR} and {MANIFEST_PATH}")


if __name__ == "__main__":
    build()
