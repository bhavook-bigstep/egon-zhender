// console-tour.mjs — DETAILED walkthrough of the Prince Houston WS-1 PII-flagging console.
// Voice-only, native/Retina (dsf:2). Explains each feature as it's shown.
//
//   PLAYWRIGHT_CORE=$(npm root -g)/playwright/node_modules/playwright-core/index.mjs \
//     DEMO_BASE_URL=http://127.0.0.1:8000 node console-tour.mjs ~/demo-chrome-profile ./out record
//   FAST=1 ... → quick selector/flow validation, writes the authoritative cues.
import { open } from '../.claude/skills/demo-video/scripts/web/record-lib.mjs'

const [profile, outDir, mode] = process.argv.slice(2)
if (!profile || !outDir) { console.error('usage: console-tour.mjs <profile> <out-dir> [record]'); process.exit(1) }
const BASE = process.env.DEMO_BASE_URL
if (!BASE) { console.error('set DEMO_BASE_URL'); process.exit(1) }
const sleep = ms => new Promise(r => setTimeout(r, ms))

const CPS = 18, TAIL = 500
const FAST = !!process.env.FAST
const hold = t => FAST ? 40 : Math.round(t.length / CPS * 1000) + TAIL

const d = await open({ profile, outDir, record: mode === 'record', url: BASE + '/',
                       width: 1920, height: 1080, dsf: 2, captions: false })

async function line (t) { await d.say(t, hold(t)); await d.hide(); await sleep(120) }
async function explain (sel, t) { await d.box(sel); await line(t); await d.unbox(); await sleep(120) }
async function nav (href, proof) {
  await d.click(`.sidenav-nav a[href="${href}"]`)
  await d.page.waitForSelector(proof, { timeout: 15000 })
  await d.overlays(); await sleep(400)
}
async function closeDialog (id) {
  await d.page.locator(`#${id} [data-close]`).first().click().catch(() => {})
  await d.page.waitForSelector(`#${id}[open]`, { state: 'detached', timeout: 5000 }).catch(() => {})
  await sleep(350)
}

// ========================= Landing hero =========================
await d.page.waitForSelector('.hero-title', { timeout: 20000 })
await d.overlays(); await sleep(400)
await line('Let me walk you through the Prince Houston data cleansing console, feature by feature.')
await explain('.hero-title',
  'Prince Houston was acquired, and its legacy document corpus has to be screened for sensitive data before it is cleared.')
await explain('.grid.entry',
  'The work is two workstreams: one flags sensitive data, live here; two, coming next, matches people records.')

// ========================= Run — the source browser =========================
await d.click('a.card.tile[href="/run"]')
await d.page.waitForSelector('#run-selected', { timeout: 15000 })
await d.page.waitForSelector('.rowcheck', { timeout: 15000 }).catch(() => {})
await d.overlays(); await sleep(400)
await explain('.table-wrap',
  'Workstream one opens on the authorised corpus, read from a frozen Databricks manifest of the files we are cleared to scan.')
await explain('.table-wrap',
  'It is metadata only, the id, file type and available fields. Nothing sensitive shows here, and the source is never modified.')
await explain('#rows-pager',
  'The whole corpus is paged through here, and every format is handled, from PDFs and Office files to scanned images.')
// pick one fast text document (gold-0000) and run it LIVE
const r0 = d.page.locator('#rows tr').filter({ hasText: 'gold-0000' }).first()
if (await r0.count()) await r0.locator('.rowcheck').check().catch(() => {})
else await d.click('.rowcheck')
await explain('#run-selected',
  'You tick the documents to scan and run them. One file can stream step by step, or several queue as a background batch.')
await d.click('#run-selected')
await d.page.waitForSelector('#run-dialog[open]', { timeout: 8000 }).catch(() => {})
await sleep(400)
await line('For a single file you choose: watch the pipeline run live, or queue it and keep working while it finishes.')
// --- live run ---
await d.click('#run-live')
await d.page.waitForSelector('#timeline', { timeout: 15000 })
await d.overlays(); await sleep(500)
await explain('#timeline',
  'Here it runs live. Each stage fires in order: ingest, extract, the OCR gate, detection, the semantic screen, then the model.')
await line('Every stage streams to the screen as it completes, so a reviewer can see exactly how the decision was reached.')
const finished = await d.page.waitForSelector('#to-workbook', { state: 'visible', timeout: 60000 })
  .then(() => true).catch(() => false)
await d.overlays(); await sleep(500)
if (finished) {
  await explain('#live-outcome',
    'And it finishes with the flag, its category and the strongest signal, the exact row that then lands in Records.')
} else {
  await line('Each finished stage records its outcome, and the result lands as one explainable row in Records.')
}

// ========================= Jobs — monitor + reconciliation =========================
await nav('/jobs', '#jobs-body')
await explain('.tiles',
  'The Jobs page is the run monitor. These tiles reconcile the whole corpus end to end.')
await explain('.tiles',
  'Authorised versus processed, how many were flagged, not flagged, or could not be read, so nothing is silently dropped.')
await explain('#jobs-body',
  'Below is every run, single or batch, with its status, progress, and a reproducible run id.')
// open a run's scoped results overlay
await d.page.locator('button[data-job-results]').first().click().catch(() => {})
await d.page.waitForSelector('#job-dialog[open]', { timeout: 8000 }).catch(() => {})
await sleep(600)
await line('Opening a run shows exactly the rows it produced, scoped to that run, with flag status, categories and the strongest signal.')
await closeDialog('job-dialog')

// ========================= Records — review hub =========================
await nav('/records', '#records-body')
await d.page.waitForSelector('button[data-details]', { timeout: 15000 })
await explain('.table-wrap',
  'The Records hub is where review happens, the latest result for every document, deduplicated across all runs.')
await explain('#records-sort',
  'You sort by the review queue, least confident first, so reviewers spend their time where the model is unsure.')
await explain('.controls',
  'The full result set exports to Excel, CSV or JSON, and can be filtered by review status.')
await explain('.adj-cell',
  'Reviewers adjudicate right in the table, accept, reject or ask for more information, and a decision resets if a later run changes that file.')
// open one record's explainable findings
let opened = false
try {
  const row = d.page.locator('#records-body tr').filter({ hasText: 'gold-0001' }).first()
  if (await row.count()) { await row.locator('button[data-details]').click(); opened = true }
} catch {}
if (!opened) await d.page.locator('button[data-details]').first().click()
await d.page.waitForSelector('#record-dialog .finding-card', { timeout: 15000 })
await sleep(600)
await line('Opening a record shows every finding behind its flag, and none of it is a black box.')
await line('Each finding carries its category, which evaluator found it, and the exact evidence location.')
await line('That evaluator is a deterministic recogniser, Presidio, the semantic screen, or the language model, each catching different data.')
await line('Evidence is cited by location, never the raw value, so it is verifiable against the source without the sensitive text leaking.')
await closeDialog('record-dialog')

// ========================= Recognizers — extend detection =========================
await nav('/recognizers', '#rec-form')
await explain('#rec-form',
  'Detection is not fixed. You can extend it here, without touching code.')
await explain('#rec-form',
  'A recogniser is a name, the entity it finds, a taxonomy category to flag it under, and a pattern to match.')
await explain('input[name="context"]',
  'Context words nearby can lift a weak pattern, so a loose match only counts when the surrounding text supports it.')
await d.pick('#rec-validator', 'weighted_modulus').catch(() => {})
await d.page.waitForSelector('#wm-params:not([hidden])', { timeout: 8000 }).catch(() => {})
await d.overlays(); await sleep(300)
await explain('#wm-params',
  'An optional checksum validates each match, like a card or IBAN check digit, defined purely as data, never as runnable code.')
await explain('#rec-body',
  'Here is one already live, a SWIFT BIC recogniser, the same one flagging codes back in the records.')

// ========================= Evaluate — measured quality =========================
await nav('/evaluate', '#eval-tiles')
await explain('#eval-tiles',
  'Finally, quality is measured, not asserted. Every run is scored against a golden truth set.')
await explain('#eval-tiles',
  'Flag precision, recall and F1 show how often the console is right, and how much it misses.')
await explain('#eval-breakdown-body',
  'It breaks down per category, and splits scanned from born-digital, so you see exactly where it is strong or weak.')
await explain('#eval-breakdown-body',
  'Calibration is tracked too, so a score stays provisional until there is enough labelled data to trust it.')

// ========================= Recap =========================
await line('That is the console end to end: read only over the source, every flag explainable and scored, and every run reproducible.')
await sleep(1600)

await d.finish('demo.srt')
