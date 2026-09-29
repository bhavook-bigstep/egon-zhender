# Critical Patterns

Patterns that have caused (or nearly caused) a data-quality or privacy incident on
this engagement. This file starts nearly empty and grows over time. Add an entry
when: a real incident's root cause is a code/process pattern, a near-miss is caught
in review, a debug session runs longer than ~2 hours, or the same mistake is made by
2+ people.

**Format:** Name — the failure mode — the specific prevention.

## Patterns

1. **Source mutation** — Any write, redact, merge, or overwrite against a Prince
   Houston or Zendai record breaches the RFP scope boundary and corrupts the client's
   data of record.
   → Open source read-only; emit to a separate result set; assert no source path is
   ever opened for write.

2. **Sensitive content in logs** — Logging document text, an evidence snippet, OCR
   output, or a raw identifier to aid debugging leaks real PII into log aggregation,
   where it is retained and indexed.
   → Log the source ID + non-identifying metadata only; route loggable output through
   the shared redaction helper; scrub at the logger.

3. **Uncontrolled inference egress** — Sending content (or a prompt built from content)
   to an external/managed model endpoint without written approval sends PII off-boundary.
   → Default to open-weight models on customer-controlled/dedicated infra; gate any
   external endpoint behind explicit written approval and identifier hashing.
   → The approval gate ALONE is insufficient (review 2026-09-29): egress control is three
   fail-closed layers — (1) written approval, (2) identifier minimisation (keyed-hash
   email/phone/LinkedIn *before* transfer, per Contract 2), and (3) a boundary decision
   derived/validated from the destination host, never a free-standing `is_local` flag.
   See `docs/solutions/security/inference-egress-minimisation.md`.

4. **Unescaped server values on a UI/SSE surface** — Injecting a server-derived value
   (source_id, run_id, reason text) into the DOM via `innerHTML` on a page that displays
   sensitive metadata/findings. Legacy-corpus ids derive from client filenames (untrusted),
   so markup in one executes script on the operator's screen — which could exfiltrate the
   on-screen PII off-boundary (a Contract 2 egress incident). Near-miss caught in review
   2026-09-29.
   → Build rows with `createElement` + `textContent` (never `innerHTML` for server data);
   set ids as `data-*` properties; keep every UI/SSE surface metadata-only (evidence by
   location, no matched string / OCR text / raw identifiers). See
   `docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md`.

<!-- Add new incident-derived patterns below. Keep each one: Name — failure mode — prevention. -->
