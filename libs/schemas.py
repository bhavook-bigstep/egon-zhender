"""Row, finding, manifest, and config shapes shared across the PoC pipelines.

Every pipeline boundary validates against these models so row-shape drift cannot
hide (`.claude/rules/python.md`). No model here stores sensitive content: findings
reference evidence by LOCATION only (`.claude/rules/privacy-sensitive-data.md`).
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def _is_local_host(url: str) -> bool:
    """True when the URL's host is loopback/local (no egress)."""
    host = urlparse(url).hostname or ""
    return host in _LOCAL_HOSTS


class FlagStatus(StrEnum):
    """Per-item outcome (response §3.2)."""

    FLAGGED = "flagged"
    NOT_FLAGGED = "not_flagged"
    UNABLE_TO_PROCESS = "unable_to_process"


class ProcessingStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class ScoreType(StrEnum):
    """How a finding was detected (response §3.3)."""

    DETERMINISTIC_MATCH = "deterministic_match"
    SIMILARITY = "similarity"
    MODEL_SCORE = "model_score"
    CLASSIFIER_SCORE = "classifier_score"


class Band(StrEnum):
    DETERMINISTIC = "deterministic"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CalibrationStatus(StrEnum):
    CALIBRATED = "calibrated"
    PROVISIONAL = "provisional"
    NOT_CALIBRATED = "not_calibrated"
    NOT_APPLICABLE = "not_applicable"


class ExceptionCode(StrEnum):
    """Typed processing exceptions — never a silent drop (`data-pipeline.md`)."""

    NOT_IN_MANIFEST = "not_in_manifest"
    HASH_MISMATCH = "hash_mismatch"
    UNSUPPORTED_TYPE = "unsupported_type"
    UNREADABLE = "unreadable"
    EXTRACTION_ERROR = "extraction_error"
    OCR_FAILURE = "ocr_failure"
    DETECTION_ERROR = "detection_error"
    INTERNAL_ERROR = "internal_error"


class EvidenceLocation(BaseModel):
    """Where a finding was seen — never the sensitive string itself."""

    page: int | None = None
    sheet: str | None = None
    cell: str | None = None
    char_start: int | None = None
    char_end: int | None = None


class ManifestEntry(BaseModel):
    """One authorised source item in the frozen manifest (Contract 4)."""

    source_id: str
    content_type: str
    content_hash: str  # sha256 hex of the source bytes
    path: str  # relative path within the sample source root
    author: str | None = None
    datetime: str | None = None
    linked_executive: str | None = None
    linked_project: str | None = None


class Finding(BaseModel):
    """One sensitivity finding — content-free (evidence by location only)."""

    source_id: str
    finding_id: str
    category: str
    reason_code: str
    reason_text: str  # non-sensitive template text; never the matched string
    score_type: ScoreType
    calibration_status: CalibrationStatus
    evidence_location: EvidenceLocation
    detector_version: str
    # None for SIMILARITY (routing signal) and deterministic matches.
    band: Band | None = None
    rule_id: str | None = None
    threshold_version: str | None = None
    score: float | None = None  # 0-100 for AI; 0-1 for SIMILARITY; None for deterministic


class Ws1Summary(BaseModel):
    """One output row per input item (response §3.4 ws1_item_summary)."""

    source_id: str
    snapshot_id: str
    content_type: str
    flag_status: FlagStatus
    sensitivity_categories: list[str]
    reason_summary: str
    processing_status: ProcessingStatus
    calibration_status: CalibrationStatus
    content_hash: str
    run_id: str
    config_version: str
    author: str | None = None
    datetime: str | None = None
    linked_executive: str | None = None
    linked_project: str | None = None
    strongest_band: Band | None = None
    strongest_score_type: ScoreType | None = None
    strongest_score: float | None = None
    exception_code: ExceptionCode | None = None


class ReconcileReport(BaseModel):
    """Run-level reconciliation (Contract 4): one row per input, counts balance."""

    input_count: int
    flagged: int
    not_flagged: int
    unable_to_process: int
    one_row_per_input: bool
    reconciled: bool


# --- Configuration models (versioned; no literals in code — `python.md`) ---


class SourceConfig(BaseModel):
    backend: str
    root: str
    manifest: str


class InferenceConfig(BaseModel):
    provider: str  # mock | openweight
    model_version: str
    approval_written: bool = False
    is_local: bool = True  # local/dedicated infra vs a managed endpoint
    base_url: str | None = None  # openweight: OpenAI-compatible endpoint
    api_key_env: str | None = None  # openweight: env var holding the key (never inline)
    # EZ-held key (env var name) for hashing identifiers before hosted transfer (Contract 2).
    hash_key_env: str | None = None
    mock_hints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _boundary_consistency(self) -> InferenceConfig:
        """Fail closed: is_local must agree with base_url's host (egress guard)."""
        if self.base_url and self.is_local and not _is_local_host(self.base_url):
            raise ValueError(
                "inference.is_local=true but base_url points at a non-local host; "
                "set is_local=false (managed endpoint, approval-gated) or use a local URL"
            )
        return self


class ExtractConfig(BaseModel):
    engine: str = "decode"  # decode | native | docling | tika
    docling_url: str | None = None  # docling engine: service base URL
    tika_url: str | None = None  # tika engine: service base URL


class OcrGateConfig(BaseModel):
    min_text_density: float = 0.15
    min_printable_ratio: float = 0.85
    max_image_coverage: float = 0.5


class OcrConfig(BaseModel):
    provider: str = "stub"  # stub | docling
    url: str | None = None  # docling: OCR service base URL


class RecogniserConfig(BaseModel):
    rule_id: str
    category: str
    pattern: str  # regex; matches synthetic tokens only in the PoC sample
    reason_code: str


class DetectConfig(BaseModel):
    engine: str = "regex"  # regex | presidio | presidio_http
    recognisers: list[RecogniserConfig] = Field(default_factory=list)  # regex engine
    # presidio engine (in-process or presidio_http):
    presidio_language: str = "en"
    presidio_score_threshold: float = 0.35  # min confidence for NER entities
    presidio_url: str | None = None  # presidio_http: analyzer service base URL
    # Auditable detector version stamped on findings; bump when the image/model changes.
    detector_version: str = "detect-presidio-0.1"
    category_map: dict[str, str] = Field(default_factory=dict)  # entity_type -> category
    deterministic_entities: list[str] = Field(default_factory=list)  # checksum-validated


class TaxonomyConfig(BaseModel):
    version: str
    categories: list[str]


class SemanticConfig(BaseModel):
    enabled: bool = False
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    route_threshold: float = 0.35
    threshold_version: str = "sem-0"
    examples: dict[str, list[str]] = Field(default_factory=dict)  # category -> phrases


class CalibrationConfig(BaseModel):
    artefact: str | None = None  # path to a fitted calibration artefact
    version: str = "cal-0"
    min_positives: int = 100
    max_holdout_error: float = 5.0  # calibration error budget, in points (0-100)
    method: str = "sigmoid"  # sigmoid | isotonic


class ScoringConfig(BaseModel):
    # A finding is created only at/above flag_threshold (see assess). The LOW band is
    # therefore [flag_threshold, band_medium) by construction — no separate band_low.
    flag_threshold: float = 40.0
    band_high: float = 80.0
    band_medium: float = 60.0
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)


class OutputConfig(BaseModel):
    result_dir: str
    format: str = "jsonl"


class Ws1Config(BaseModel):
    config_version: str
    seed: int
    source: SourceConfig
    inference: InferenceConfig
    ocr_gate: OcrGateConfig
    ocr: OcrConfig = Field(default_factory=OcrConfig)
    taxonomy: TaxonomyConfig
    detect: DetectConfig
    scoring: ScoringConfig
    output: OutputConfig
    extract: ExtractConfig = Field(default_factory=ExtractConfig)
    semantic: SemanticConfig = Field(default_factory=SemanticConfig)
    # DEMO/synthetic only. When true, the review UI reveals the matched value (re-derived
    # live from the read-only source, never persisted). MUST stay false for real data —
    # it surfaces PII. The base/production configs leave it false (content-free default).
    reveal_matched_content: bool = False
