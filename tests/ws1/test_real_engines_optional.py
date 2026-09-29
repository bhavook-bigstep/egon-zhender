"""Optional integration tests for the real heavy engines.

Skipped automatically when the ML dependencies (requirements-ml.txt) are absent, so the
default hermetic suite stays light. They only assert the real engine runs and returns
the right shape — not specific detections.
"""

from __future__ import annotations

import pytest


def test_presidio_engine_runs_if_installed() -> None:
    pytest.importorskip("presidio_analyzer")
    from libs.schemas import DetectConfig
    from pipelines.workstream1_sensitive.detect_presidio import PresidioEngine

    engine = PresidioEngine(
        DetectConfig(
            engine="presidio",
            category_map={"CREDIT_CARD": "financial"},
            deterministic_entities=["CREDIT_CARD"],
        )
    )
    findings = engine.analyze("my card is 4111111111111111", "x")
    assert isinstance(findings, list)


def test_docling_extractor_live_if_running() -> None:
    from libs.schemas import ManifestEntry
    from pipelines.workstream1_sensitive.errors import PipelineItemError
    from pipelines.workstream1_sensitive.extract_docling import DoclingHttpExtractor

    extractor = DoclingHttpExtractor("http://localhost:5001")
    entry = ManifestEntry(
        source_id="live", content_type="text/plain", content_hash="h", path="note.txt"
    )
    try:
        result = extractor.extract(entry, b"Reference ACCT-123456 in this note.\n")
    except PipelineItemError as exc:
        pytest.skip(f"docling-serve not reachable: {exc}")
    assert isinstance(result.text, str)


def test_presidio_http_live_if_running() -> None:
    from libs.schemas import DetectConfig
    from pipelines.workstream1_sensitive.detect_presidio_http import PresidioHttpEngine
    from pipelines.workstream1_sensitive.errors import PipelineItemError
    from pipelines.workstream1_sensitive.extract import ExtractedText

    engine = PresidioHttpEngine(
        DetectConfig(
            engine="presidio_http",
            presidio_url="http://localhost:3001",
            category_map={"CREDIT_CARD": "financial"},
            deterministic_entities=["CREDIT_CARD"],
        )
    )
    try:
        findings = engine.analyze(
            ExtractedText(source_id="live", text="My card is 4095-2609-9393-4932")
        )
    except PipelineItemError as exc:  # service not reachable → typed error
        pytest.skip(f"presidio not reachable: {exc}")
    assert any(f.category == "financial" for f in findings)


def test_tika_extractor_live_if_running() -> None:
    import io

    from docx import Document

    from libs.schemas import ManifestEntry
    from pipelines.workstream1_sensitive.errors import PipelineItemError
    from pipelines.workstream1_sensitive.extract_tika import TikaHttpExtractor

    document = Document()
    document.add_paragraph("Legacy content with ACCT-123456 token")
    buffer = io.BytesIO()
    document.save(buffer)
    entry = ManifestEntry(
        source_id="live",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content_hash="h",
        path="legacy.docx",
    )
    extractor = TikaHttpExtractor("http://localhost:9998")
    try:
        result = extractor.extract(entry, buffer.getvalue())
    except PipelineItemError as exc:
        pytest.skip(f"tika not reachable: {exc}")
    assert "ACCT-123456" in result.text


def test_sbert_embedder_runs_if_installed() -> None:
    pytest.importorskip("sentence_transformers")
    from pipelines.workstream1_sensitive.semantic import SbertEmbedder

    embedder = SbertEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    vectors = embedder.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0
