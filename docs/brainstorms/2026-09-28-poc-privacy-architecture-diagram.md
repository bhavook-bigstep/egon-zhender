# Brainstorm: PoC Privacy-First Architecture Diagram (components, data flow, workflows)

- **Date:** 2026-09-28
- **Prompt:** Explore the PoC with data privacy front-and-centre; create the Excalidraw
  diagram of components to be used, and the data flow / workflows for both workstreams.

## Deliverable

- **Excalidraw (open/edit):** https://excalidraw.com/#json=hNlNATR4wmy2ajlEGzrSq,-BAt3iXsQRrizA_Bor5PMw
- **In repo:** `docs/diagrams/ph-poc-architecture.excalidraw`

The canvas uses the data-protection boundary as the organising principle: a red-dashed
**trust boundary**, an **HMAC hashing gate** (only hashed IDs cross), an **approval-gated
external-inference** box, evidence-by-location outputs, and a cross-cutting
governance/audit band. Both workstream pipelines flow left→right inside the processing
boundary.

## Problem Frame

INTAKE SUMMARY

```
Goal:        Produce a privacy-first architecture picture for the PoC — components,
             data flow, and workflows for both workstreams — with the data-protection
             boundary as the organising principle.
Workstream:  Both (WS1 sensitive-data + WS2 matching) + shared libs/governance.
Inputs:      Frozen Databricks snapshot — ~330k file notes, ~90k docs (~55 GB),
             ~88k people vs ~1.5M Zendai. Read-only.
Sensitivity: Whole corpus treated as PII (financial, health, gov-ID, compensation,
             legal, client-confidential).
Method:      WS1 extract -> OCR-gate -> Presidio -> semantic+LLM -> score/band.
             WS2 normalise -> hashed deterministic keys -> blocking -> Splink -> rate.
Output:      A diagram artefact (this brainstorm), not code.
Governance:  Frozen manifest + versioned config + run ledger + reconciliation + audit.
Constraints: Read-only source; no external inference without written approval;
             minimise/hash before hosted transfer; PoC time-box (target 1 Nov 2026).
```

- **In scope (this exploration):** the diagram + data-flow/workflow narrative.
- **Out of scope:** pipeline code; real taxonomy sub-categories (released post-contract);
  production scale-out (Contract 5).

## Prior Art

- **Internal (cite `path:line`):** pipeline sequences are already fixed in
  `pipelines/workstream1_sensitive/CLAUDE.md:14-24` and
  `pipelines/workstream2_matching/CLAUDE.md:14-22`; the trust-boundary/deployment split
  and HMAC minimisation come from our submitted response
  (`docs/requirement/EZ_PH_DC_2026_01_Agentics_Response.docx`, §4.1, §9.1-9.3).
  `docs/solutions/INDEX.md` is empty — no prior learnings to reuse. The diagram
  **restates** our own committed design; the only new decision is *how to frame it*.
- **External:** see per-approach citations below.

## Approaches

### Approach A — Trust-boundary DFD (privacy zones as the frame) — BUILT
- **Idea:** One canvas; the security boundary, hashing gate and approval gate are
  first-class shapes; both pipelines sit inside the processing zone.
- **Fit with contracts:** read-only source, minimisation, controlled inference,
  explainable+scored outputs and reproducibility are all *visible*, not implied.
- **Effort / Risk:** Low-Med / a single busy canvas.
- **Source:** LINDDUN PRO Privacy Threat Modeling Tutorial — DistriNet/KU Leuven —
  https://downloads.linddun.org/tutorials/pro/v0/tutorial.pdf (accessed 2026-09-28):
  model a privacy system as a DFD of processes/stores/external-entities/flows plus
  **trust boundaries**, then elicit linkability/identifiability/disclosure threats per
  element. And: Microsoft Threat Modeling Tool — Getting Started — Microsoft Learn —
  https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-getting-started
  (accessed 2026-09-28): **trust boundaries are red dotted lines** marking where data
  crosses a privilege level.

### Approach B — Two swimlane flowcharts (one per workstream) + a separate deployment diagram
- **Idea:** Privacy shown as an annotation lane rather than the frame; clearest
  per-stage reading.
- **Fit with contracts:** good stage clarity; privacy becomes secondary.
- **Effort / Risk:** Med (3 diagrams) / boundary story fragmented across pages.
- **Source:** **No source found — this is an AI-generated idea** (standard swimlane
  practice; no specific source adds value). Kept as a good large-format D1 follow-up.

### Approach C — C4-style component/container model
- **Idea:** Container diagram (Databricks / processing / inference / results), then a
  component drill-down per workstream.
- **Fit with contracts:** strong for engineers; weaker at showing data-in-motion
  privacy controls, which is the client's concern.
- **Effort / Risk:** Med-High / over-built for a PoC brainstorm.
- **Source:** C4 model — Simon Brown — https://c4model.com/ (accessed 2026-09-28):
  container/component decomposition.

### Supporting method citations (used in the diagram content)
- **Splink — The Fellegi-Sunter Model** — MoJ Analytical Services —
  https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html
  (accessed 2026-09-28): deterministic keys + blocking before Fellegi-Sunter scoring (WS2).
- **Presidio — Adding recognizers** — Microsoft —
  https://microsoft.github.io/presidio/analyzer/adding_recognizers/ (accessed 2026-09-28):
  predefined + custom checksum/context recognizers (WS1 Detect).
- **Hash functions for pseudonymisation** — EDPS/AEPD —
  https://www.edps.europa.eu/sites/default/files/publication/19-10-30_aepd-edps_paper_hash_final_en.pdf
  (accessed 2026-09-28), with **NIST SP 800-224 (HMAC)** —
  https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-224.ipd.pdf:
  keyed-hash pseudonymisation before transfer, re-identification retained by the key holder (WS2 §4.1).
- **OCR only when no text layer** — Apify (born-digital PDF text-layer extraction) —
  https://apify.com/scrapesage/ocr-text-extractor/examples/ocr-pdf-text-layer-fast-extraction
  (accessed 2026-09-28): OCR only true scans. *Vendor page, not a primary standard — the
  gate's density/printable-ratio thresholds are calibrated in the PoC.*

## Comparison

| Approach | Effort | Risk | Source / AI-generated |
| -------- | ------ | ---- | --------------------- |
| A — Trust-boundary DFD | Low-Med | Single busy canvas | Cited (LINDDUN, MS TMT) |
| B — Swimlanes + deployment | Med | Privacy story fragmented | AI-generated |
| C — C4 model | Med-High | Over-built; weak on data-in-motion | Cited (C4) |

## Data Flow / Workflow (as drawn)

- **WS1 (blue lane):** `SOURCE -(read-only)-> Ingest` (MIME+hash vs frozen manifest)
  `-> Extract` (native/Tika/Docling, no macros) `-> OCR gate` (PaddleOCR only when the
  text layer is absent/poor) `-> Detect` (Presidio + custom recognisers) `-> Assess`
  (semantic screen + LLM, minimal span only) `-> Score/Band` (deterministic vs AI)
  `-> one WS1 row` (evidence by location, never content). External inference endpoint
  reachable only after written approval.
- **WS2 (purple lane):** `SOURCE -(read-only)-> Normalise`; the minimisation notebook
  runs inside EZ, HMAC-hashing email/phone/LinkedIn so only hashed IDs cross the
  boundary `-> Deterministic keys -> Blocking` (bounds 88k x ~1.5M) `-> Splink`
  (Fellegi-Sunter) `-> Conflict rules -> Rate` (Confirmed…No match) `-> one WS2 row`.
- **Cross-cutting:** versioned config drives every stage; every stage writes the run
  ledger; counts reconcile (inputs == output rows); audit is append-only with no raw content.

## Recommendation

**Approach A (built).** The RFP's decisive concern is *where sensitive data goes and what
protects it at each crossing*; a trust-boundary DFD makes that the subject of the
picture, matches the "privacy front-and-centre" ask, and fits the PoC time-box.
Approach B is a good large-format follow-up for the D1 design review.

**Next step:** `/ph-poc:plan "<implementation slice>"` when moving from the picture to
pipeline scaffolding. Optionally refine the diagram with a Deployment A vs B panel.
