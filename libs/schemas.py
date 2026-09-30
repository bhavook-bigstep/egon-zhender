"""Row, finding, manifest, and config shapes shared across the PoC pipelines.

Every pipeline boundary validates against these models so row-shape drift cannot
hide (`.claude/rules/python.md`). No model here stores sensitive content: findings
reference evidence by LOCATION only (`.claude/rules/privacy-sensitive-data.md`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
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
    backend: str  # sample | databricks
    root: str  # sample: local dir · databricks: UC volume base /Volumes/<cat>/<schema>/<vol>
    manifest: str  # path to the frozen manifest, relative to root for the databricks backend
    profile: str | None = None  # databricks: named auth profile (else env/OAuth default)


class InferenceConfig(BaseModel):
    provider: str  # mock | openweight | anthropic
    model_version: str
    approval_written: bool = False
    is_local: bool = True  # local/dedicated infra vs a managed endpoint
    base_url: str | None = None  # openweight: OpenAI-compatible endpoint
    # Chat-completions path appended to base_url. Default suits vLLM/Ollama; Gemini's
    # OpenAI-compat shim uses base_url ".../v1beta/openai" + chat_path "/chat/completions".
    chat_path: str = "/v1/chat/completions"
    api_key_env: str | None = None  # openweight: env var holding the key (never inline)
    # EZ-held key (env var name) for hashing identifiers before hosted transfer (Contract 2).
    hash_key_env: str | None = None
    # Max characters of the extracted text sent to the model per span (data minimisation vs
    # coverage). PoC: a single larger span; production would chunk a long document.
    max_span_chars: int = 512
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
    provider: str = "stub"  # stub | docling | preprocess
    url: str | None = None  # docling/preprocess: OCR service base URL
    # preprocess provider: rasterise PDFs + clean images before OCR (degraded-scan recovery).
    dpi: int = 200  # PDF rasterisation resolution
    deskew: bool = True
    denoise: bool = True
    binarize: bool = True


class RecogniserConfig(BaseModel):
    rule_id: str
    category: str
    pattern: str  # regex; matches synthetic tokens only in the PoC sample
    reason_code: str


class PatternSpec(BaseModel):
    """One regex pattern inside a custom Presidio recogniser."""

    name: str
    regex: str
    score: float = 0.5  # base confidence for a raw match (context can boost it)


class ChecksumSpec(BaseModel):
    """Declarative parameters for the `weighted_modulus` checksum — a DATA-ONLY way to add a
    check-digit scheme (ISO 7064 family, ABA, ISBN, many national IDs) without executing any
    user code. Two shapes: a weighted digit sum mod m, or the whole value read as one integer
    mod m (IBAN-style, with an optional rotation). Evaluated by libs.checksums."""

    mode: Literal["weighted_sum", "integer"] = "weighted_sum"
    modulus: int = Field(ge=2)  # the check base (10, 11, 97, ...)
    expect: int = Field(default=0, ge=0)  # required remainder (0, or 1 for IBAN)
    weights: list[int] = Field(default_factory=list)  # weighted_sum: cycled across chars
    align: Literal["left", "right"] = "left"  # weighted_sum: cycle from the left or the right
    alphabet: Literal["digits", "alnum"] = "digits"  # alnum: 0-9 + A-Z -> 10..35 (ISO 7064)
    rotate: int = Field(default=0, ge=0)  # integer mode: move first N chars to the end

    @model_validator(mode="after")
    def _coherent(self) -> ChecksumSpec:
        if self.expect >= self.modulus:
            raise ValueError("expect must be < modulus")
        if self.mode == "weighted_sum" and not self.weights:
            raise ValueError("weighted_sum requires at least one weight")
        return self


class CustomRecogniserConfig(BaseModel):
    """A user-defined Presidio PatternRecogniser, added to the DEFAULT recognisers per
    /analyze request (ad-hoc). Map `supported_entity` to a taxonomy category via
    `category_map`; add it to `deterministic_entities` if the regex is a validated format."""

    name: str
    supported_entity: str  # the entity_type it emits (e.g. SWIFT_BIC) — map via category_map
    patterns: list[PatternSpec]
    context: list[str] = Field(default_factory=list)  # nearby words that boost confidence
    supported_language: str = "en"
    # Optional checksum validator: a libs.checksums.VALIDATORS key (luhn|iban_mod97|aba_routing),
    # or "weighted_modulus" parameterised by `checksum`. Set → a match is verified: pass →
    # DETERMINISTIC_MATCH, fail → dropped.
    validator: str | None = None
    checksum: ChecksumSpec | None = None  # params when validator == "weighted_modulus"


class DetectConfig(BaseModel):
    engine: str = "regex"  # regex | presidio | presidio_http
    recognisers: list[RecogniserConfig] = Field(default_factory=list)  # regex engine
    # presidio engine (in-process or presidio_http):
    presidio_language: str = "en"
    presidio_score_threshold: float = 0.35  # min confidence for NER entities
    presidio_url: str | None = None  # presidio_http: analyzer service base URL
    # User-defined recognisers ADDED to Presidio's defaults per request (ad-hoc). Closes
    # gaps in the built-in set (e.g. SWIFT/BIC, bank routing, PIN) without a container rebuild.
    custom_recognizers: list[CustomRecogniserConfig] = Field(default_factory=list)
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


class BatchConfig(BaseModel):
    """Operational knobs for batch runs. NOT result-affecting: output is sorted by
    source_id before writing, so the same manifest + config + seed yields identical
    bytes regardless of concurrency (Contract 4). Kept out of the run_id for the same
    reason. A per-request value (CLI --max-concurrency) overrides these defaults."""

    # I/O-bound pipeline (LLM / docling / presidio / Databricks over HTTP), so threads
    # overlap the waits; a modest default avoids swamping the shared LLM/service caps.
    max_concurrency: int = 4
    batch_size: int = 500  # items per checkpoint (resume granularity)


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
    batch: BatchConfig = Field(default_factory=BatchConfig)
    extract: ExtractConfig = Field(default_factory=ExtractConfig)
    semantic: SemanticConfig = Field(default_factory=SemanticConfig)
    # DEMO/synthetic only. When true, the review UI reveals the matched value (re-derived
    # live from the read-only source, never persisted). MUST stay false for real data —
    # it surfaces PII. The base/production configs leave it false (content-free default).
    reveal_matched_content: bool = False
