# Citations & Sourcing Rules

Applies to every new idea, approach, fix, recommendation, or non-obvious design
suggestion Claude proposes in this repo — in brainstorming, planning, reviews,
implementation notes, and chat answers alike. On this engagement that especially
covers method choices: OCR gating heuristics, recogniser design, semantic/LLM
screening, Splink blocking rules, and calibration methods.

## HARD BLOCKS (reject if violated)

1. **Every proposed idea must carry a source tag** — Each new idea, fix, or
   suggestion is presented with EITHER a real cited source OR an explicit
   "no source found" disclaimer. An idea with neither is a blocking failure;
   do not present it that way.
2. **You MUST actually web-search before claiming a source or its absence** —
   Use `WebSearch` / `WebFetch`. Do not assert "no source found" without having
   genuinely searched, and do not assert a source from memory. If web tools are
   unavailable in the current context, say so explicitly rather than guessing.
3. **Never fabricate a citation** — No invented URLs, titles, authors, dates, or
   paper names. A made-up citation is worse than an honest disclaimer. If unsure
   a source says what you claim, fetch and verify it or drop it.

## REQUIRED PATTERNS

- **Citation format:** `Title — publisher/author — URL (accessed YYYY-MM-DD)`,
  followed by one line stating how the source supports the idea.
- **Disclaimer format (verbatim):**
  **"No source found — this is an AI-generated idea."**
  Optionally add one line on the reasoning behind the idea.
- **Prefer primary/authoritative sources:** official docs (Presidio, Splink, Docling,
  PaddleOCR, Tika), standards/RFCs, peer-reviewed papers (e.g. Fellegi-Sunter), or the
  library's own repo — over aggregator blogs and forums.
- **Match the claim to the source:** a source about X does not justify a claim
  about Y. Cite the specific part that applies.
- **Scope:** cite novel or contestable claims (methods, trade-offs, "best practice"
  assertions, accuracy/perf/privacy claims). Trivial or self-evident statements
  (basic syntax, restating the request, obvious refactors) do not need a citation —
  but if in doubt, tag it.

## SUPPRESSIONS (do NOT flag)

- Statements about THIS repository's own code, contracts, or files (self-evident
  from the codebase — cite the `path:line` instead of the web).
- Direct restatements of the RFP, the response, or the user's own instructions
  (cite `docs/requirement/...` instead of the web).
- Trivial language/framework syntax that any reference would confirm.
