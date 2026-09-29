"""Shared fixtures for WS-1 tests. Synthetic data only (testing rules)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml

from libs.schemas import ManifestEntry
from pipelines.workstream1_sensitive.runner import RunResult, run

# Sensitive synthetic tokens that must never appear in outputs or logs.
SENSITIVE_TOKENS = ("ACCT-123456", "salary", "GOVID-AB123456", "Passport", "passport")


class DictReader:
    """An in-memory SourceReader for unit tests (read-only, no filesystem)."""

    def __init__(
        self, entries: list[ManifestEntry], blobs: dict[str, bytes]
    ) -> None:
        self._entries = entries
        self._blobs = blobs

    def list_manifest(self) -> list[ManifestEntry]:
        return list(self._entries)

    def open_item(self, source_id: str) -> bytes:
        if source_id not in self._blobs:
            raise KeyError(source_id)
        return self._blobs[source_id]

    def open_stream(self, source_id: str) -> Iterator[bytes]:
        yield self.open_item(source_id)


@pytest.fixture
def run_ws1(tmp_path: Path) -> Callable[..., RunResult]:
    """Run the full WS-1 pipeline against the repo sample into a temp result dir."""

    def _run(subdir: str = "out") -> RunResult:
        base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
        base["output"]["result_dir"] = str(tmp_path / subdir)
        cfg_path = tmp_path / f"ws1-{subdir}.yaml"
        cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
        return run(cfg_path)

    return _run
