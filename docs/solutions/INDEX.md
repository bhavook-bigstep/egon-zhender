# Solutions Index

Institutional memory. **Search this file before implementing.** Each solved,
non-trivial problem is captured here via `/project:compound`.

Categories map to subfolders under `docs/solutions/`.

## bugs
- [Interactive SSE — deterministic-id PK collision + worker-thread hang](bugs/ws1-interactive-sse-concurrency.md) — re-run collided on the registry PK and a worker raise hung the stream; fix = `upsert` + `try/finally`.

## patterns
- [One-process web UI — SQLite queue + worker + SSE + metadata-only surface](patterns/ws1-web-ui-sse-sqlite-queue.md) — portable, infra-light, API/CLI-first UI + admin monitor; the shape to reuse for WS-2.

## integrations
- [WS-1 real engines behind ports via Docker](integrations/ws1-real-engines-http-adapters.md) — Docling/Presidio/Tika as HTTP adapters (injectable clients, verify live API, pin digests).

## performance
_(none yet)_

## security
- [Inference egress needs minimisation + boundary validation](security/inference-egress-minimisation.md) — approval gate alone is insufficient; hash identifiers + validate boundary, all fail-closed.

## matching
_(none yet)_

---

To add an entry: run `/project:compound` after solving a non-trivial problem. It
writes the doc and appends a one-line link here under the right category.
