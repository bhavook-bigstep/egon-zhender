"""Build the WS-1 GOLDEN DATASET — a tangible, labelled, multi-format corpus.

Source content: NVIDIA Nemotron-PII (synthetic, span-labelled, CC BY 4.0) — see NOTICE.md.
We sample a balanced slice, map its PII labels to our approved taxonomy
(financial / government_id / health), render each record into a real document format
(txt / born-digital PDF / scanned PNG for OCR / DOCX / XLSX), and also GENERATE clean
PII-free documents — so the set has a realistic mixture:

  * flagged            — contains in-taxonomy PII (financial / government_id / health)
  * not_flagged (PII)  — contains only out-of-taxonomy PII (name / email / phone / …)
  * not_flagged (clean)— no PII at all (generated)

Ground truth is keyed on the entity VALUE + type/category (not char offsets), so it
survives PDF/OCR reformatting. Output is versioned files under datasets/ws1_golden/,
shaped for a clean Databricks load (a documents/source table + a labels/truth table):

    documents/<source_id>.<ext>   the rendered files
    manifest.jsonl                one row per document (source table)
    labels.jsonl                  one row per ground-truth entity (truth table)

Deterministic given the upstream dataset. Run from the repo root:
    python datasets/ws1_golden/build_golden_dataset.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import random
import textwrap
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUT_DIR = Path("datasets/ws1_golden")
DOCS_DIR = OUT_DIR / "documents"
MANIFEST_PATH = OUT_DIR / "manifest.jsonl"
LABELS_PATH = OUT_DIR / "labels.jsonl"

_DATASET = "nvidia/Nemotron-PII"
_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    f"?dataset={_DATASET}&config=default&split=train&offset={{off}}&length=100"
)
_POOL_OFFSETS = (0, 100, 200, 300, 400, 500, 600, 700)  # deterministic pool (~800 rows)

# Nemotron label -> our approved taxonomy category. Everything else is out-of-taxonomy
# (real PII, but not one of the three flagged categories — a true negative for flagging).
_CATEGORY_MAP = {
    # financial
    "account_number": "financial",
    "bank_routing_number": "financial",
    "credit_debit_card": "financial",
    "cvv": "financial",
    "pin": "financial",
    "swift_bic": "financial",
    # government_id
    "ssn": "government_id",
    "tax_id": "government_id",
    "certificate_license_number": "government_id",
    "license_plate": "government_id",
    "vehicle_identifier": "government_id",
    # health
    "blood_type": "health",
    "health_plan_beneficiary_number": "health",
    "medical_record_number": "health",
}
_TAXONOMY = ("financial", "government_id", "health")

# How many of each bucket to include (deterministic; capped by availability).
_QUOTA = {"financial": 12, "government_id": 12, "health": 8, "out_of_taxonomy": 8}
# Born-digital (text layer) + scanned (image-only / degraded → OCR path) — a realistic mix.
_FORMATS = ("txt", "pdf", "png", "docx", "xlsx", "scan_pdf", "scan_jpg")

_CLEAN_DOCS = [
    "Prince Houston file note\nQuarterly delivery review completed. Roadmap priorities and "
    "general availability were discussed. No client-specific details recorded.",
    "Meeting minutes\nThe team agreed on the sprint scope and confirmed the release window. "
    "Action items are tracked in the shared board. No further follow-up required.",
    "Internal memo\nOffice closure dates for the upcoming period are confirmed. Facilities "
    "will circulate the updated calendar. This note contains no personal information.",
    "Project update\nThe migration rehearsal met its success criteria on the sample. "
    "Throughput and reconciliation looked healthy. Proceeding to the next milestone.",
    "Status report\nAll workstreams are green this week. Documentation was refreshed and "
    "the onboarding guide reviewed. Nothing sensitive to report.",
    "Announcement\nThe knowledge-sharing session is scheduled for next month. Topics cover "
    "tooling and best practices. Attendance is optional and open to all teams.",
    "Retrospective notes\nWhat went well: steady progress and clear ownership. What to "
    "improve: earlier reviews. No personal or confidential data appears in this note.",
    "General correspondence\nThank you for the productive workshop. We will share the "
    "summary deck and next steps shortly. Please reach out with any high-level questions.",
]

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


def _as_spans(value: object) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                continue
    return []


def _wrap(text: str, width: int = 70) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [text]:
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


# --- renderers (one document per record) ---


def render_txt(text: str) -> bytes:
    return text.encode("utf-8")


def render_pdf(title: str, text: str) -> bytes:
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, 730, title)
    pdf.setFont("Helvetica", 11)
    y = 705
    for line in _wrap(text, 90):
        pdf.drawString(72, y, line)
        y -= 18
        if y < 72:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = 730
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _text_image(text: str) -> Image.Image:
    lines = _wrap(text, 64)
    font = _font(28)
    img = Image.new("RGB", (960, 60 + 42 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((36, 28 + 42 * i), line, fill="black", font=font)
    return img


def render_png(text: str) -> bytes:
    buf = BytesIO()
    _text_image(text).save(buf, format="PNG")
    return buf.getvalue()


# --- scanned (degraded) renderers: skew, blur, low contrast, sensor noise, JPEG artefacts.
# Deterministic per document (seeded), so the corpus is reproducible.
_SEVERITY = {
    "light": {"angle": 1.5, "blur": 0.6, "contrast": 0.92, "noise": 8},
    "medium": {"angle": 3.0, "blur": 1.1, "contrast": 0.78, "noise": 18},
    "heavy": {"angle": 5.0, "blur": 1.9, "contrast": 0.62, "noise": 32},
}


def _degrade(img: Image.Image, seed: int, severity: str) -> Image.Image:
    """Apply scan-like distortion (grayscale, skew, blur, contrast loss, noise)."""
    cfg = _SEVERITY[severity]
    rng = random.Random(seed)
    npr = np.random.default_rng(seed)
    grey = img.convert("L")
    grey = grey.rotate(rng.uniform(-cfg["angle"], cfg["angle"]), expand=True, fillcolor=255)
    grey = grey.filter(ImageFilter.GaussianBlur(radius=cfg["blur"]))
    grey = ImageEnhance.Contrast(grey).enhance(cfg["contrast"])
    arr = np.asarray(grey).astype(np.int16)
    arr = np.clip(arr + npr.normal(0, cfg["noise"], arr.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("RGB")


def render_scan_jpg(text: str, seed: int, severity: str) -> bytes:
    """A degraded scanned image, saved as JPEG (adds compression artefacts)."""
    buf = BytesIO()
    _degrade(_text_image(text), seed, severity).save(buf, format="JPEG", quality=55)
    return buf.getvalue()


def render_scan_pdf(text: str, seed: int, severity: str) -> bytes:
    """An IMAGE-ONLY PDF (a scanned page, no text layer) — forces the OCR path."""
    page = _degrade(_text_image(text), seed, severity)
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    w, h = LETTER
    iw, ih = page.size
    scale = min((w - 72) / iw, (h - 72) / ih)
    pdf.drawImage(
        ImageReader(page), 36, h - 36 - ih * scale, iw * scale, ih * scale
    )  # no drawString → no text layer
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def render_docx(title: str, text: str) -> bytes:
    doc = Document()
    doc.add_heading(title, level=1)
    for para in text.splitlines() or [text]:
        doc.add_paragraph(para)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_xlsx(text: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "record"
    ws.append(["content"])
    for line in text.replace(". ", ".\n").splitlines():
        if line.strip():
            ws.append([line.strip()])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


_CONTENT_TYPE = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "png": "image/png",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "scan_jpg": "image/jpeg",  # degraded scanned image
    "scan_pdf": "application/pdf",  # image-only (scanned) PDF, no text layer
}
_EXT = {"txt": "txt", "pdf": "pdf", "png": "png", "docx": "docx", "xlsx": "xlsx",
        "scan_jpg": "jpg", "scan_pdf": "pdf"}


def _render(fmt: str, title: str, text: str) -> bytes:
    if fmt == "txt":
        return render_txt(text)
    if fmt == "pdf":
        return render_pdf(title, text)
    if fmt == "png":
        return render_png(text)
    if fmt == "docx":
        return render_docx(title, text)
    return render_xlsx(text)


def _fetch_pool() -> list[dict]:
    """Fetch the deterministic row pool from the upstream dataset."""
    pool: list[dict] = []
    for off in _POOL_OFFSETS:
        with urllib.request.urlopen(_ROWS_URL.format(off=off), timeout=60) as resp:
            data = json.load(resp)
        for record in data.get("rows", []):
            pool.append(record["row"])
    return pool


def _bucket(spans: list[dict]) -> tuple[str, set[str]]:
    """Return (primary_bucket, in-taxonomy categories present)."""
    cats = {
        _CATEGORY_MAP[s["label"]]
        for s in spans
        if s.get("label") in _CATEGORY_MAP
    }
    for category in _TAXONOMY:  # priority order fills buckets deterministically
        if category in cats:
            return category, cats
    return "out_of_taxonomy", cats


def build() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    pool = _fetch_pool()

    # Deterministic bucketing (sorted by uid for stability).
    buckets: dict[str, list[dict]] = {k: [] for k in _QUOTA}
    for row in sorted(pool, key=lambda r: r.get("uid", "")):
        spans = _as_spans(row.get("spans"))
        if not spans:
            continue
        primary, _ = _bucket(spans)
        if len(buckets[primary]) < _QUOTA[primary]:
            buckets[primary].append(row)

    selected = [row for bucket in _QUOTA for row in buckets[bucket]]

    manifest: list[dict] = []
    labels: list[dict] = []
    total = len(selected) + len(_CLEAN_DOCS)
    fmt_cycle = iter(_FORMATS * (total // len(_FORMATS) + 1))
    sev_cycle = iter(["light", "medium", "heavy"] * (total // 3 + 1))

    def emit(source_id: str, text: str, title: str, meta: dict, spans: list[dict]) -> None:
        fmt = next(fmt_cycle)
        seed = int(source_id.split("-")[1])
        scanned = fmt in ("scan_jpg", "scan_pdf")
        severity = next(sev_cycle) if scanned else None
        if fmt == "scan_jpg":
            data = render_scan_jpg(text, seed, severity)
        elif fmt == "scan_pdf":
            data = render_scan_pdf(text, seed, severity)
        else:
            data = _render(fmt, title, text)
        filename = f"{source_id}.{_EXT[fmt]}"
        (DOCS_DIR / filename).write_bytes(data)
        cats = sorted(
            {_CATEGORY_MAP[s["label"]] for s in spans if s.get("label") in _CATEGORY_MAP}
        )
        manifest.append(
            {
                "source_id": source_id,
                "content_type": _CONTENT_TYPE[fmt],
                "content_hash": hashlib.sha256(data).hexdigest(),
                "path": f"documents/{filename}",
                "scanned": scanned,  # image-only/degraded → exercises the OCR path
                "scan_severity": severity,
                "expected_flag_status": "flagged" if cats else "not_flagged",
                "expected_categories": cats,
                "has_pii": bool(spans),
                "source_dataset": meta["source_dataset"],
                "source_uid": meta.get("source_uid"),
                "domain": meta.get("domain"),
                "document_type": meta.get("document_type"),
                "document_format": meta.get("document_format"),
                "locale": meta.get("locale"),
            }
        )
        for span in spans:
            label = span.get("label", "")
            category = _CATEGORY_MAP.get(label)
            labels.append(
                {
                    "source_id": source_id,
                    "entity_type": label,
                    "category": category or "out_of_taxonomy",
                    "in_taxonomy": category is not None,
                    "value": span.get("text", ""),
                }
            )

    index = 0
    for row in selected:
        source_id = f"gold-{index:04d}"
        emit(
            source_id,
            row.get("text", ""),
            row.get("document_type") or "Document",
            {
                "source_dataset": _DATASET,
                "source_uid": row.get("uid"),
                "domain": row.get("domain"),
                "document_type": row.get("document_type"),
                "document_format": row.get("document_format"),
                "locale": row.get("locale"),
            },
            _as_spans(row.get("spans")),
        )
        index += 1

    for clean in _CLEAN_DOCS:  # PII-free negatives (generated)
        source_id = f"gold-{index:04d}"
        emit(
            source_id,
            clean,
            "Internal Note",
            {"source_dataset": "generated-clean", "source_uid": None,
             "domain": "internal", "document_type": "note", "document_format": "unstructured",
             "locale": "us"},
            [],
        )
        index += 1

    manifest.sort(key=lambda r: r["source_id"])
    labels.sort(key=lambda r: (r["source_id"], r["entity_type"]))
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row) + "\n")
    with LABELS_PATH.open("w", encoding="utf-8") as handle:
        for row in labels:
            handle.write(json.dumps(row) + "\n")

    flagged = sum(1 for r in manifest if r["expected_flag_status"] == "flagged")
    with_pii_neg = sum(
        1 for r in manifest if r["expected_flag_status"] == "not_flagged" and r["has_pii"]
    )
    clean = sum(1 for r in manifest if not r["has_pii"])
    print(f"wrote {len(manifest)} documents to {DOCS_DIR}")
    print(f"  flagged={flagged}  not_flagged(has PII)={with_pii_neg}  clean(no PII)={clean}")
    print(f"  {len(labels)} ground-truth entity rows -> {LABELS_PATH}")


if __name__ == "__main__":
    build()
