# Plan: WS-1 console IA — sidebar shell + run wizard + unified Records hub

- **Date:** 2026-09-30
- **Author:** Claude
- **Status:** draft

## Intake Summary

```
Goal:        Reorganise the WS-1 web UI into a task-oriented "console": a persistent
             left-sidebar shell, a guided run wizard, and ONE unified master-detail
             Records hub — replacing the "everything under /admin" grab-bag and the two
             overlapping results surfaces, so navigation is natural.
Workstream:  WS1 web app only (app/) — NO pipeline/method change.
Inputs:      Existing routes/pages + existing APIs (records, reviews, reveal, eval,
             recognizers, SSE streams). Same read-only Databricks/sample source.
Sensitivity: Metadata-only surfaces; matched content only via the existing gated, lazy
             per-record reveal (Contract 2). No content on list views.
Method:      Front-end IA + a small records-scoping API filter; server-rendered Jinja +
             vendored HTMX + native SSE + safe-DOM JS (no new build step, no CDN).
Output:      Same result rows/findings; the §3.4 export moves onto Records.
Governance:  No config editing in the UI (thresholds/taxonomy stay versioned — Contract 4).
             Reproducibility/ledger untouched. Old routes 30x-redirect to new ones.
Constraints: PoC time-box; Contract 5 (this is demo-UX repositioning, not method — sizable
             front-end, no method risk); Contract 2 reveal stays gated; anti-XSS (safe DOM).
```

**Scope note (Contract 5):** this is a UI/IA rework of the demo surface, not pipeline work.
It's sizeable front-end but touches no contract-sensitive logic (reveal, config, source
read-only, reproducibility all unchanged). Sources/Outputs sidebar items are added as
**disabled "coming soon"** placeholders to reserve homes for the A′ output-sink work —
no behaviour behind them here.

## Prior Learnings

**Internal:** `docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md` (the one-process
UI shell + metadata-only rule — the surface this restructures); the recent
`docs/solutions/bugs/ws1-live-view-pipeline-catchall-event.md` (live-view event model —
the wizard's Progress step reuses the fixed stepper). Contracts: root `CLAUDE.md`
Contract 2 (reveal gated), Contract 4 (no ad-hoc threshold/taxonomy editing in UI),
critical-pattern #4 (safe DOM — build rows with `createElement`+`textContent`, never
`innerHTML` for server data). Current pages/routes confirmed in `app/main.py` +
`app/templates/`.

**External (web-searched):**
- Task-oriented top-level nav, 6–7 items, mutually-exclusive labels — [Information
  Architecture Study Guide — NN/g — https://www.nngroup.com/articles/ia-study-guide/](https://www.nngroup.com/articles/ia-study-guide/)
  (accessed 2026-09-30).
- Persistent left-sidebar console shell for 6+ sections; one nav tree, drawer on mobile —
  [UX navigation design: patterns & best practices — Eleken — https://www.eleken.co/blog-posts/ux-navigation-design](https://www.eleken.co/blog-posts/ux-navigation-design)
  (accessed 2026-09-30).
- Linear wizard with visible progress + Back/Next for a structured process — [Wizard design
  guidelines — PatternFly — https://www.patternfly.org/components/wizard/design-guidelines/](https://www.patternfly.org/components/wizard/design-guidelines/)
  (accessed 2026-09-30).
- Master-detail + single-source-of-truth to remove duplicate record views — [The
  Master–Detail Interface Pattern — Appli — https://appli.io/the-master-detail-interface-pattern/](https://appli.io/the-master-detail-interface-pattern/)
  and [Single source of truth — Wikipedia — https://en.wikipedia.org/wiki/Single_source_of_truth](https://en.wikipedia.org/wiki/Single_source_of_truth)
  (accessed 2026-09-30).

## Approach

Restructure the shell, route to task sections, guide the run, and unify results. No new
backend beyond a records-scoping filter + a per-record findings endpoint. (CERTAIN unless
tagged.)

### Target IA
Sidebar sections (≤7): **Run · Jobs · Records · Recognizers · Evaluate** (+ disabled
**Sources**, **Outputs**). Top bar keeps the brand + the global jobs 🔔. Flow:
`Run (wizard) → single ▶ Progress ▶ Records · batch ▶ Jobs ▶ Records`.

### S — Shell (sidebar + top bar)
- `app/templates/base.html` — restructure `<body>` to a shell: `<aside class="sidenav">`
  (include `_sidebar.html`) + `<div class="app-main">` (top bar with brand + 🔔 + page
  title, then `{% block content %}`). Keep `#toasts`, footer.
- NEW `app/templates/_sidebar.html` — nav list from a fixed set; active item via an
  `active` context var (already passed to admin pages). Mobile: a `#nav-toggle` button
  opens the sidebar as a drawer (`app.js`).
- `app/static/app.css` — shell grid (`.sidenav` fixed left, `.app-main` right), collapse
  to drawer under 860px; active-item styling; keep Egon Zehnder theme. (CERTAIN)

### N — Routes & redirects (`app/main.py`)
- New canonical page routes reusing existing handlers/templates under the shell:
  `/run` (wizard), `/jobs` (monitor), `/records` (hub), `/recognizers`, `/evaluate`.
- 303/307 redirects (no dead links): `/`→`/run`, `/ws1`→`/run`, `/admin`→`/jobs`,
  `/admin/workbook`→`/records`, `/admin/eval`→`/evaluate`, `/admin/recognizers`→`/recognizers`,
  `/jobs/{job_id}`→`/records?job={job_id}`. Keep `/ws1/live` (wizard Progress) — add
  `/run/live` alias. Retire `hero.html` (route redirects).
- Each page passes `active="<section>"` for sidebar highlighting.

### J — Jobs (monitor)
- `/jobs` renders the migration tiles + jobs table (today's `/admin` = `admin.html` +
  `_admin_header.html` tiles/bar). Move the tiles into a small `_stats_tiles.html` partial
  used here; drop the `_admin_header.html` tab strip (sidebar replaces tabs). Same SSE
  (`/api/admin/stream`). Clicking a job row → `/records?job=<id>`.

### W — Run wizard (`/run`)
- `app/templates/run.html` — a 3-step stepper (reusing the pipeline-stepper CSS):
  **1 Select** (the paginated source browser from `ws1.html`/`_rows.html` — checkbox
  select or "whole manifest") → **2 Review & submit** (read-only config summary:
  taxonomy version, thresholds, model, reveal state, + the existing hosted-model approval
  banner; choose **single** = interactive or **batch** = queued) → **3 Progress**
  (single → the live stepper from `live.html`; batch → link to `/jobs`).
- Step 2 is **read-only** — the UI never edits thresholds/taxonomy (Contract 4). (CERTAIN)
- `app.js` `initRunWizard()` drives step visibility + Back/Next; reuses `initWs1` submit
  + `initLive`.

### R — Records hub (master-detail) — the biggest piece
- `app/templates/records.html` — replaces `admin_workbook.html` + `results.html`:
  a filter bar (scope: **latest-per-record** | a job; status; review state; the existing
  uncertainty sort) + a records **list** (left/top) + a **detail drawer** (right) that
  shows one record's findings (category · score-type · band · evidence **location**),
  the gated **lazy reveal**, provenance, and the **adjudication** controls
  (accept/reject/needs-info + rationale). §3.4 export buttons stay here.
- `app.js` — extend `renderRecords`/`applyRecordsView` (already built) to open the detail
  drawer on row click; migrate the finding-dialog + `revealDialog` logic (from
  `results.html`/`initDialogs`) into the drawer; keep adjudication + uncertainty sort.
- `app/main.py` APIs:
  - `GET /api/admin/records?job=<id>` — when `job` is set, return **that job's** rows
    (via `_load_rows_findings`) merged with reviews, else `_records_with_reviews()`
    (latest-per-record). NEW helper `_records_for_job(job_id)`.
  - `GET /api/records/{source_id}/findings?job=<id>` — content-free findings for one
    record (category, score_type, band, evidence location, reason) for the drawer.
    (PROBABLE on exact shape.)
  - Reuse `GET /api/jobs/{job_id}/reveal?source_id=` unchanged for the gated reveal.
- Retire `results.html` (its content lives in the drawer); `/jobs/{id}` redirects to
  `/records?job=`.

### Recognizers / Evaluate
- Move `admin_recognizers.html` / `admin_eval.html` bodies under the shell (drop the
  `_admin_header` tab strip; sidebar handles nav). Content + APIs unchanged.

## Tasks

| # | Task | Files | Depends on | Parallel? |
| - | ---- | ----- | ---------- | --------- |
| S1 | Shell layout + sidebar partial | `base.html`, `_sidebar.html`, `app/static/app.css` | — | yes |
| S2 | Sidebar drawer + active-section JS | `app/static/app.js`, `app.css` | S1 | no |
| N1 | Canonical routes + redirects + retire hero | `app/main.py` | S1 | no |
| J1 | Jobs monitor page + stats-tiles partial | `app/main.py`, `_stats_tiles.html`, `admin.html`→jobs | S1, N1 | no |
| W1 | Run wizard template + step nav | `app/templates/run.html`, `app/static/app.js`/`.css` | S1, N1 | no |
| R1 | Records API: `?job=` filter + findings endpoint | `app/main.py` | — | yes |
| R2 | Records hub template (list + drawer) | `app/templates/records.html`, `app/static/app.css` | S1, R1 | no |
| R3 | Records JS: drawer, migrate findings/reveal, adjudication | `app/static/app.js` | R2 | no |
| C1 | Recognizers/Evaluate under shell (drop tabs) | `admin_recognizers.html`, `admin_eval.html`, `_admin_header.html` (remove) | S1 | yes |
| T1 | Update/add tests | `tests/app/test_pages.py` | all | no |

Parallel front: **S1, R1, C1**. Then S2/N1 → J1/W1/R2 → R3 → T1.

## Tests

- [ ] **Redirects:** `/`, `/ws1`, `/admin`, `/admin/workbook`, `/admin/eval`,
  `/admin/recognizers`, `/jobs/<id>` all 30x to their new targets (assert `location`).
- [ ] **Shell:** every page renders the sidebar (`class="sidenav"`) with the correct
  `active` item; the 🔔 stays global.
- [ ] **Run wizard:** `/run` renders step 1 (source list) + the stepper; the config
  summary is read-only (no threshold inputs); submit still creates a job.
- [ ] **Records hub:** `/records` lists latest-per-record; `/records?job=<id>` (or
  `/api/admin/records?job=`) returns that job's rows; the detail findings endpoint is
  content-free (no `SENSITIVE_TOKENS`); reveal stays gated (empty when off); adjudication
  round-trips; export includes review columns; **no content leak** on the list.
- [ ] **Metadata-only:** assert no matched content on `/records` or its list API without
  reveal (reuse the existing `SENSITIVE_TOKENS` checks).
- [ ] Existing eval/recognizers/reviews tests still pass under the new routes.

## Risks & Rollback

- **Route churn breaks bookmarks/tests** → keep every old path as a 30x redirect; update
  tests to follow. Rollback: routes are additive; old templates can be re-pointed.
- **Records unification is the big migration** (two pages → one) → do R1 (API) first, then
  build the hub beside the old pages, cut `/jobs/{id}`→`/records?job=` last; keep
  `results.html` until the drawer reaches parity (findings + reveal + provenance).
- **Reveal / XSS** → reuse the existing gated lazy reveal endpoint + safe-DOM builders
  (critical-pattern #4); never render server strings via `innerHTML`.
- **Scope/time (Contract 5)** → no pipeline/method change; if time-boxed, ship S+N+J+R
  (shell + records) first and defer the wizard (W) to a follow-up (Run can stay the
  current browser under the shell until then).

## Review Notes

_(filled in after implementation / review)_
