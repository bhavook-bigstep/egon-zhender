"""Integration: an image item with no OCR sidecar reconciles as unable_to_process."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from libs.hashing import sha256_hex
from pipelines.workstream1_sensitive.runner import run


def test_ocr_failure_reconciles_as_unable(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    # Image bytes (not UTF-8) with NO co-located .ocr.txt sidecar → OCR failure.
    image_bytes = bytes.fromhex("89504e470d0a1a0a") + b"\x00NO-SIDECAR\x00"
    (sample_dir / "scan.png").write_bytes(image_bytes)

    manifest = [
        {
            "source_id": "scan_x",
            "content_type": "image/png",
            "content_hash": sha256_hex(image_bytes),
            "path": "scan.png",
        }
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["source"]["root"] = str(sample_dir)
    base["source"]["manifest"] = str(manifest_path)
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")

    result = run(cfg_path)

    assert len(result.summaries) == 1
    summary = result.summaries[0]
    assert summary.flag_status.value == "unable_to_process"
    assert summary.exception_code is not None
    assert summary.exception_code.value == "ocr_failure"
    assert result.reconcile.reconciled
    assert result.reconcile.unable_to_process == 1
    # No ocr_gate stage event is recorded when the gate itself raises.
    assert not any(event.stage == "ocr_gate" for event in result.ledger.events)
