"""WS-1 runner — deterministic orchestration over a frozen manifest.

Reads a versioned config, processes each authorised item through the stages, records
a run ledger, reconciles counts, and writes the result set. A per-item failure yields
a typed `unable_to_process` row rather than a silent drop (Contracts 3 and 4).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from libs.audit.ledger import RunLedger, StageEvent
from libs.audit.redaction import safe_stage_message
from libs.calibration import Calibrator
from libs.config import load_ws1_config
from libs.inference.base import InferenceProvider
from libs.inference.mock import MockProvider
from libs.inference.openweight import HttpChatClient, OpenWeightProvider
from libs.schemas import (
    ExceptionCode,
    Finding,
    ManifestEntry,
    ReconcileReport,
    Ws1Config,
    Ws1Summary,
)
from libs.source.base import SourceReader
from libs.source.sample import SampleTestEnvReader
from pipelines.workstream1_sensitive.assess import assess
from pipelines.workstream1_sensitive.detect import (
    DetectionEngine,
    build_detection_engine,
)
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_engine import (
    ExtractionEngine,
    build_extraction_engine,
)
from pipelines.workstream1_sensitive.ingest import ingest
from pipelines.workstream1_sensitive.ocr_gate import (
    OCRProvider,
    StubOCRProvider,
    apply_ocr_gate,
)
from pipelines.workstream1_sensitive.output import write_ledger, write_outputs
from pipelines.workstream1_sensitive.score import finalize_scored, summarise
from pipelines.workstream1_sensitive.semantic import SbertEmbedder, SemanticScreen

logger = logging.getLogger("ws1.runner")


@dataclass
class RunResult:
    run_id: str
    summaries: list[Ws1Summary]
    findings: list[Finding]
    reconcile: ReconcileReport
    summary_path: Path
    findings_path: Path
    ledger_path: Path
    ledger: RunLedger


@dataclass
class Ws1Context:
    """A built, reusable set of stage dependencies (warm context).

    Built once from a config and shared by both the batch `run()` and the job runner,
    so single and bulk paths execute the identical per-item core.
    """

    cfg: Ws1Config
    reader: SourceReader
    provider: InferenceProvider
    ocr: OCRProvider
    extraction_engine: ExtractionEngine
    detection_engine: DetectionEngine
    screen: SemanticScreen | None
    calibrator: Calibrator


def build_context(cfg: Ws1Config) -> Ws1Context:
    """Construct all stage dependencies from a validated config."""
    return Ws1Context(
        cfg=cfg,
        reader=build_reader(cfg),
        provider=build_provider(cfg),
        ocr=build_ocr(cfg),
        extraction_engine=build_extraction_engine(cfg.extract),
        detection_engine=build_detection_engine(cfg.detect),
        screen=build_semantic_screen(cfg),
        calibrator=build_calibrator(cfg),
    )


def build_reader(cfg: Ws1Config) -> SourceReader:
    if cfg.source.backend == "sample":
        return SampleTestEnvReader(cfg.source.root, cfg.source.manifest)
    raise ValueError(f"unsupported source backend: {cfg.source.backend}")


def build_provider(cfg: Ws1Config) -> InferenceProvider:
    if cfg.inference.provider == "mock":
        return MockProvider(
            model_version=cfg.inference.model_version,
            approval_written=cfg.inference.approval_written,
            hints=cfg.inference.mock_hints,
        )
    if cfg.inference.provider == "openweight":
        if not cfg.inference.base_url:
            raise ValueError("openweight provider requires inference.base_url")
        api_key = (
            os.environ.get(cfg.inference.api_key_env)
            if cfg.inference.api_key_env
            else None
        )
        client = HttpChatClient(cfg.inference.base_url, api_key=api_key)
        return OpenWeightProvider(
            client=client,
            model_version=cfg.inference.model_version,
            is_local=cfg.inference.is_local,
            approval_written=cfg.inference.approval_written,
        )
    raise ValueError(f"unsupported inference provider: {cfg.inference.provider}")


def build_semantic_screen(cfg: Ws1Config) -> SemanticScreen | None:
    if not cfg.semantic.enabled:
        return None
    return SemanticScreen(
        embedder=SbertEmbedder(cfg.semantic.model),
        examples=cfg.semantic.examples,
        route_threshold=cfg.semantic.route_threshold,
        threshold_version=cfg.semantic.threshold_version,
    )


def build_calibrator(cfg: Ws1Config) -> Calibrator:
    if cfg.scoring.calibration.artefact:
        return Calibrator.load(cfg.scoring.calibration.artefact)
    return Calibrator.empty()


def build_ocr(cfg: Ws1Config) -> OCRProvider:
    if cfg.ocr.provider == "stub":
        return StubOCRProvider(cfg.source.root)
    if cfg.ocr.provider == "docling":
        from pipelines.workstream1_sensitive.ocr_http import HttpOcrProvider

        if not cfg.ocr.url:
            raise ValueError("ocr provider 'docling' requires ocr.url")
        return HttpOcrProvider(cfg.ocr.url)
    raise ValueError(f"unsupported ocr provider: {cfg.ocr.provider}")


def compute_run_id(entries: list[ManifestEntry], cfg: Ws1Config) -> str:
    """Deterministic run ID from the manifest + config version + seed."""
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.source_id):
        digest.update(entry.source_id.encode("utf-8"))
        digest.update(entry.content_hash.encode("utf-8"))
    digest.update(cfg.config_version.encode("utf-8"))
    digest.update(str(cfg.seed).encode("utf-8"))
    return digest.hexdigest()[:12]


def process_item(
    ctx: Ws1Context,
    entry: ManifestEntry,
    run_id: str,
    snapshot_id: str,
    ledger: RunLedger,
) -> tuple[Ws1Summary, list[Finding]]:
    """The shared per-item core used by both the batch run and the job runner."""
    cfg = ctx.cfg
    try:
        data = ingest(ctx.reader, entry)
        extracted = ctx.extraction_engine.extract(entry, data)
        ledger.record_stage_event(
            StageEvent(
                source_id=entry.source_id,
                stage="extract",
                outcome=cfg.extract.engine,
            )
        )
        extracted = apply_ocr_gate(entry, extracted, cfg.ocr_gate, ctx.ocr, data)
        ledger.record_stage_event(
            StageEvent(
                source_id=entry.source_id,
                stage="ocr_gate",
                outcome="ocr" if extracted.ocr_used else "skipped",
                detail={
                    "printable_ratio": extracted.printable_ratio,
                    "image_coverage": extracted.image_coverage,
                },
            )
        )
        deterministic = ctx.detection_engine.analyze(extracted)
        if ctx.screen is not None:
            similarity_findings, routed = ctx.screen.screen(
                entry.source_id, extracted.text
            )
        else:
            similarity_findings, routed = [], set(cfg.taxonomy.categories)
        model = assess(
            extracted, routed, cfg.scoring, ctx.provider, cfg.inference.hash_key_env
        )
        scored = finalize_scored(deterministic + model, cfg.scoring, ctx.calibrator)
        findings = scored + similarity_findings
        summary = summarise(
            entry,
            findings,
            exception_code=None,
            coverage_complete=extracted.coverage_complete,
            cfg=cfg.scoring,
            run_id=run_id,
            config_version=cfg.config_version,
            snapshot_id=snapshot_id,
        )
    except PipelineItemError as err:
        ledger.record_stage_event(
            StageEvent(
                source_id=entry.source_id,
                stage="pipeline",
                outcome="failed",
                exception_code=err.code,
            )
        )
        summary = summarise(
            entry,
            findings=[],
            exception_code=err.code,
            coverage_complete=False,
            cfg=cfg.scoring,
            run_id=run_id,
            config_version=cfg.config_version,
            snapshot_id=snapshot_id,
        )
        ledger.record_final(entry.source_id, summary.flag_status)
        logger.info(safe_stage_message(entry.source_id, "pipeline", "failed"))
        return summary, []
    except Exception:  # unexpected: one typed row, never abort the batch (fail loud)
        ledger.record_stage_event(
            StageEvent(
                source_id=entry.source_id,
                stage="pipeline",
                outcome="failed",
                exception_code=ExceptionCode.INTERNAL_ERROR,
            )
        )
        summary = summarise(
            entry,
            findings=[],
            exception_code=ExceptionCode.INTERNAL_ERROR,
            coverage_complete=False,
            cfg=cfg.scoring,
            run_id=run_id,
            config_version=cfg.config_version,
            snapshot_id=snapshot_id,
        )
        ledger.record_final(entry.source_id, summary.flag_status)
        logger.info(safe_stage_message(entry.source_id, "pipeline", "internal_error"))
        return summary, []

    ledger.record_final(entry.source_id, summary.flag_status)
    logger.info(
        safe_stage_message(entry.source_id, "pipeline", summary.flag_status.value)
    )
    return summary, findings


def run(config_path: str | Path) -> RunResult:
    """Execute WS-1 over the manifest named by the config and write the result set."""
    cfg = load_ws1_config(config_path)
    # Determinism (Contract 4) comes from the sorted manifest iteration, sorted output
    # writes, and the seed folded into compute_run_id below — no RNG is used.
    ctx = build_context(cfg)

    entries = ctx.reader.list_manifest()
    run_id = compute_run_id(entries, cfg)
    snapshot_id = f"sample:{Path(cfg.source.manifest).stem}"
    ledger = RunLedger(run_id, cfg.config_version)

    summaries: list[Ws1Summary] = []
    all_findings: list[Finding] = []
    for entry in entries:
        summary, findings = process_item(ctx, entry, run_id, snapshot_id, ledger)
        summaries.append(summary)
        all_findings.extend(findings)

    reconcile = ledger.reconcile(len(entries))
    summary_path, findings_path = write_outputs(summaries, all_findings, cfg)
    ledger_path = write_ledger(ledger, reconcile, cfg)

    return RunResult(
        run_id=run_id,
        summaries=summaries,
        findings=all_findings,
        reconcile=reconcile,
        summary_path=summary_path,
        findings_path=findings_path,
        ledger_path=ledger_path,
        ledger=ledger,
    )
