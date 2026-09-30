"use strict";

// ---- toasts -------------------------------------------------------------
function toast(message, opts) {
  opts = opts || {};
  const box = document.getElementById("toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = "toast" + (opts.ok ? " ok" : "");
  el.textContent = message;
  if (opts.href) {
    const a = document.createElement("a");
    a.href = opts.href;
    a.textContent = opts.linkText || "Open";
    el.appendChild(document.createElement("br"));
    el.appendChild(a);
  }
  box.appendChild(el);
  if (!opts.sticky) setTimeout(() => el.remove(), 8000);
}

// ---- WS-1 source browser: selection + submit ---------------------------
function initWs1() {
  const root = document.getElementById("ws1");
  if (!root) return;
  const configVersion = root.dataset.configVersion;

  function selected() {
    return Array.from(document.querySelectorAll(".rowcheck:checked")).map((c) => c.value);
  }
  function refreshCount() {
    const n = selected().length;
    const label = document.getElementById("selcount");
    if (label) label.textContent = n + " selected";
  }

  // Event delegation: rows can be added later via HTMX "load more".
  document.addEventListener("change", (e) => {
    if (e.target.classList && e.target.classList.contains("rowcheck")) refreshCount();
    if (e.target.id === "select-all") {
      document.querySelectorAll(".rowcheck").forEach((c) => (c.checked = e.target.checked));
      refreshCount();
    }
  });

  const single = document.getElementById("run-single");
  if (single)
    single.addEventListener("click", () => {
      const ids = selected();
      if (ids.length !== 1) {
        toast("Select exactly one item for the live single view.");
        return;
      }
      window.location.href = "/ws1/live?source_id=" + encodeURIComponent(ids[0]);
    });

  const batch = document.getElementById("run-batch");
  if (batch)
    batch.addEventListener("click", async () => {
      const ids = selected();
      if (ids.length === 0) {
        toast("Select at least one item for a batch run.");
        return;
      }
      batch.disabled = true;
      try {
        const res = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_type: "batch",
            config_version: configVersion,
            source_ids: ids,
          }),
        });
        const job = await res.json();
        if (job.status === "failed") {
          toast("Batch rejected: " + (job.exception || "unknown error"), { sticky: true });
        } else {
          toast("Batch queued (" + ids.length + " items).", { ok: true });
          batchNotification(job.job_id, ids.length);
        }
      } catch (err) {
        toast("Submit failed: " + err);
      } finally {
        batch.disabled = false;
      }
    });
}

// ---- safe DOM helpers (never innerHTML server-derived values) ----------
function cell(text, className) {
  const td = document.createElement("td");
  if (className) td.className = className;
  td.textContent = text == null ? "—" : String(text);
  return td;
}
function chipCell(text, extraClass) {
  const td = document.createElement("td");
  const span = document.createElement("span");
  span.className = "chip" + (extraClass ? " " + extraClass : "");
  span.textContent = text == null ? "—" : String(text);
  td.appendChild(span);
  return td;
}
function scoreText(v) {
  return v == null ? "—" : Number(v).toFixed(1);
}

// ---- step-by-step pipeline view ---------------------------------------
const STEP_LABELS = {
  ingest: "Ingest",
  extract: "Extract",
  ocr_gate: "OCR gate",
  detect: "Detect",
  screen: "Semantic screen",
  assess: "LLM assess",
  score: "Score & decide",
  pipeline: "Pipeline",
};
const METRIC_LABELS = {
  bytes: "bytes",
  chars: "characters",
  printable_ratio: "printable ratio",
  image_coverage: "image coverage",
  deterministic_matches: "deterministic matches",
  routed_categories: "routed categories",
  similarity_findings: "similarity findings",
  model_findings: "model findings",
  findings: "findings",
  categories: "categories",
  strongest_score: "score",
  band: "band",
  score_type: "score type",
};
const STEP_RECORD_LABELS = {
  detect: "Entities detected (type · category · score · location)",
  screen: "Category routing — cosine similarity vs threshold",
  assess: "Model results per routed category",
};
function fmtMetric(v) {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}
function recordsTable(records) {
  const cols = Object.keys(records[0]);
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  cols.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  records.forEach((r) => {
    const tr = document.createElement("tr");
    cols.forEach((c) => {
      const td = document.createElement("td");
      const v = r[c];
      td.textContent = v == null ? "—" : String(v);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.style.marginTop = "6px";
  wrap.appendChild(table);
  return wrap;
}
// Horizontal pipeline: each step is a compact clickable node; full detail + raw output
// open in a dialog on click.
function fmtBytes(n) {
  if (n == null) return "";
  if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
function fmtDur(ms) {
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}
function stepMetric(msg) {
  const d = msg.detail || {};
  switch (msg.stage) {
    case "ingest": return fmtBytes(d.bytes);
    case "extract": return d.chars != null ? d.chars + " chars" : msg.outcome || "";
    case "ocr_gate": return msg.outcome || "";
    case "detect": { const n = d.detections || 0; return n + (n === 1 ? " hit" : " hits"); }
    case "screen": { const n = d.routed_categories || 0; return n + " routed"; }
    case "assess": { const n = d.model_findings || 0; return n + (n === 1 ? " finding" : " findings"); }
    case "score": {
      let s = msg.outcome || "";
      if (d.strongest_score != null) s += " · " + Number(d.strongest_score).toFixed(0);
      if (d.band) s += " · " + d.band;
      return s;
    }
    default: return msg.outcome || "";
  }
}
function showOutcome(el, r) {
  el.textContent = "";
  el.hidden = false;
  el.className = "live-outcome " + (r.flag_status || "");
  const label = document.createElement("strong");
  label.textContent = "Result ";
  const chip = document.createElement("span");
  chip.className = "chip " + (r.flag_status || "");
  chip.textContent = r.flag_status || "—";
  const cats = document.createElement("span");
  cats.className = "lo-cats";
  cats.textContent = (r.sensitivity_categories || []).join(", ") || "no categories";
  let scoreText2 = r.strongest_score_type || "";
  if (r.strongest_band) scoreText2 += " · " + r.strongest_band;
  if (r.strongest_score != null) scoreText2 += " · " + Number(r.strongest_score).toFixed(1);
  const score = document.createElement("span");
  score.className = "muted lo-score";
  score.textContent = scoreText2;
  el.appendChild(label);
  el.appendChild(chip);
  el.appendChild(cats);
  if (scoreText2) el.appendChild(score);
}

function _section(label) {
  const el = document.createElement("div");
  el.className = "fc-match-label";
  el.style.marginTop = "16px";
  el.textContent = label;
  return el;
}

function openStepDialog(msg, index) {
  const dlg = document.getElementById("step-dialog");
  if (!dlg) return;
  dlg.textContent = "";

  const head = document.createElement("div");
  head.className = "dialog-head";
  const left = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = "Step " + index + " · " + (STEP_LABELS[msg.stage] || msg.stage);
  const out = document.createElement("span");
  out.className = "chip" + (msg.exception_code ? " unable_to_process" : "");
  out.textContent = msg.exception_code || msg.outcome;
  left.appendChild(strong);
  left.appendChild(document.createTextNode(" "));
  left.appendChild(out);
  const close = document.createElement("button");
  close.className = "ghost icon";
  close.setAttribute("data-close", "");
  close.setAttribute("aria-label", "Close");
  close.textContent = "✕";
  head.appendChild(left);
  head.appendChild(close);
  dlg.appendChild(head);

  const body = document.createElement("div");
  body.className = "dialog-body";

  const detail = msg.detail || {};
  const keys = Object.keys(detail);
  if (keys.length) {
    const l = _section("User-level output");
    l.style.marginTop = "0";
    body.appendChild(l);
    const dl = document.createElement("dl");
    dl.className = "fc-meta";
    keys.forEach((k) => {
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = METRIC_LABELS[k] || k;
      const dd = document.createElement("dd");
      dd.textContent = fmtMetric(detail[k]);
      wrap.appendChild(dt);
      wrap.appendChild(dd);
      dl.appendChild(wrap);
    });
    body.appendChild(dl);
  }

  const records = msg.records || [];
  if (records.length) {
    body.appendChild(_section(STEP_RECORD_LABELS[msg.stage] || "Step output"));
    body.appendChild(recordsTable(records));
  }

  body.appendChild(_section("Raw step output (event)"));
  const pre = document.createElement("pre");
  pre.className = "raw-json";
  pre.textContent = JSON.stringify(msg, null, 2);
  body.appendChild(pre);

  dlg.appendChild(body);
  if (typeof dlg.showModal === "function") dlg.showModal();
}

// ---- batch progress notification (poll the job) ------------------------
function batchNotification(jobId, total) {
  const box = document.getElementById("notifications");
  if (!box) {
    toast("Batch queued: " + jobId, { ok: true, href: "/jobs/" + jobId, linkText: "View results →" });
    return;
  }
  const card = document.createElement("div");
  card.className = "card notif";
  const head = document.createElement("div");
  head.className = "notif-head";
  const title = document.createElement("span");
  title.className = "mono";
  title.textContent = jobId;
  const status = document.createElement("span");
  status.className = "chip";
  status.textContent = "queued";
  head.appendChild(title);
  head.appendChild(status);
  const bar = document.createElement("div");
  bar.className = "bar";
  const fill = document.createElement("span");
  fill.style.width = "0%";
  bar.appendChild(fill);
  const line = document.createElement("div");
  line.className = "notif-line muted";
  line.textContent = "0 / " + total;
  card.appendChild(head);
  card.appendChild(bar);
  card.appendChild(line);
  box.prepend(card);

  const terminal = ["completed", "failed", "cancelled"];
  const timer = setInterval(async () => {
    let job;
    try {
      job = await (await fetch("/api/jobs/" + encodeURIComponent(jobId))).json();
    } catch (e) {
      return;
    }
    const done = job.progress_done || 0;
    const tot = job.progress_total || total || 1;
    fill.style.width = Math.min(100, Math.round((100 * done) / Math.max(1, tot))) + "%";
    status.textContent = job.status;
    line.textContent = done + " / " + tot;
    if (terminal.includes(job.status)) {
      clearInterval(timer);
      status.className = "chip " + (job.status === "completed" ? "not_flagged" : "unable_to_process");
      if (job.result && job.result.reconcile) {
        const rc = job.result.reconcile;
        line.textContent =
          done + " / " + tot + " · " + rc.flagged + " flagged · " +
          rc.not_flagged + " not · " + rc.unable_to_process + " unable";
      }
      const a = document.createElement("a");
      a.className = "btn";
      a.href = "/jobs/" + encodeURIComponent(jobId);
      a.textContent = "View results →";
      a.style.marginTop = "12px";
      a.style.display = "inline-block";
      card.appendChild(a);
    }
  }, 1000);
}

// ---- single interactive live view (SSE) --------------------------------
function initLive() {
  const root = document.getElementById("live");
  if (!root) return;
  const sourceId = root.dataset.sourceId;
  const timeline = document.getElementById("timeline");
  const findings = document.getElementById("findings-body");
  // The stepper itself conveys progress; the old status text bar was removed. This no-op
  // wrapper keeps the status writes harmless if the element isn't present.
  const statusEl = document.getElementById("live-status");
  const status = {
    get textContent() { return statusEl ? statusEl.textContent : ""; },
    set textContent(v) { if (statusEl) statusEl.textContent = v; },
  };

  const outcome = document.getElementById("live-outcome");
  const STEP_ORDER = ["ingest", "extract", "ocr_gate", "detect", "screen", "assess", "score"];
  const nodes = {};  // stage -> its step card
  let runStart = 0;
  let runningStage = null;
  let failed = false;

  timeline.textContent = "";

  // Only ran + running steps are shown (no pending placeholders). New cards are appended
  // with a FLIP animation: existing cards slide to their new centered positions while the
  // new one slides in — so the row stays centered with a smooth side shift.
  function flipAppend(newNodes) {
    const prev = new Map();
    Array.prototype.forEach.call(timeline.children, (el) => prev.set(el, el.getBoundingClientRect().left));
    newNodes.forEach((n) => timeline.appendChild(n));
    Array.prototype.forEach.call(timeline.children, (el) => {
      if (prev.has(el)) {
        const dx = prev.get(el) - el.getBoundingClientRect().left;
        if (dx) {
          el.style.transition = "none";
          el.style.transform = "translateX(" + dx + "px)";
          requestAnimationFrame(() => {
            el.style.transition = "transform .38s ease";
            el.style.transform = "";
          });
        }
      } else {
        el.classList.add("step-in");
      }
    });
  }

  function makeRunningCard(stage) {
    const node = document.createElement("div");
    node.className = "step-node running";
    const badge = document.createElement("div");
    badge.className = "step-badge";
    const num = document.createElement("span");
    num.className = "step-badge-num";
    num.textContent = String(STEP_ORDER.indexOf(stage) + 1);
    badge.appendChild(num);
    const name = document.createElement("div");
    name.className = "step-name";
    name.textContent = STEP_LABELS[stage] || stage;
    const metric = document.createElement("div");
    metric.className = "step-metric";
    const dur = document.createElement("div");
    dur.className = "step-dur";
    node.appendChild(badge);
    node.appendChild(name);
    node.appendChild(metric);
    node.appendChild(dur);
    return node;
  }

  function advanceTo(stage) {
    const node = makeRunningCard(stage);
    flipAppend([node]);  // connectors are drawn via CSS, so no separate arrow element
    nodes[stage] = node;
    runningStage = stage;
    runStart = Date.now();
    node.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    const pos = STEP_ORDER.indexOf(stage) + 1;
    status.textContent =
      "Processing: " + (STEP_LABELS[stage] || stage) + "… (" + pos + "/" + STEP_ORDER.length + ")";
  }

  function settle(node, failLabel, metricText) {
    node.className = "step-node " + (failLabel ? "failed" : "done");
    node.querySelector(".step-badge-num").textContent = failLabel ? "✕" : "✓";
    if (metricText != null) node.querySelector(".step-metric").textContent = metricText;
    node.querySelector(".step-dur").textContent = fmtDur(Date.now() - runStart);
  }

  function stopRunning(failLabel) {
    // End the running step — mark it failed (with a label) or just settle it.
    if (!runningStage) return;
    const node = nodes[runningStage];
    if (node && node.classList.contains("running")) settle(node, failLabel, failLabel || null);
    runningStage = null;
  }

  function setDone(msg) {
    const node = nodes[msg.stage];
    if (!node) return;
    const failLabel = msg.exception_code || "";
    settle(node, failLabel, failLabel || stepMetric(msg));
    const index = STEP_ORDER.indexOf(msg.stage) + 1;
    node.setAttribute("role", "button");
    node.tabIndex = 0;
    const open = () => openStepDialog(msg, index);
    node.onclick = open;
    node.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    };
  }

  advanceTo(STEP_ORDER[0]);  // start with just the first step, running and centered

  const es = new EventSource("/api/interactive/stream?source_id=" + encodeURIComponent(sourceId));
  es.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (msg.event === "stage") {
      if (nodes[msg.stage]) {
        setDone(msg);
        if (msg.stage === runningStage) runningStage = null;
        if (msg.exception_code) {
          failed = true;
          status.textContent = "Failed at " + (STEP_LABELS[msg.stage] || msg.stage);
        } else {
          const next = STEP_ORDER[STEP_ORDER.indexOf(msg.stage) + 1];
          if (next) advanceTo(next);
          else status.textContent = "Finalising…";
        }
      } else if (msg.exception_code) {
        // Failure catch-all (e.g. stage "pipeline"): fail the step currently running so its
        // animation stops instead of spinning forever.
        failed = true;
        stopRunning(msg.exception_code);
        status.textContent = "Failed: " + msg.exception_code;
      }
    } else if (msg.event === "item") {
      const r = msg.row;
      const tr = document.createElement("tr");
      tr.appendChild(cell(r.source_id, "mono"));
      tr.appendChild(chipCell(r.flag_status, r.flag_status));
      tr.appendChild(cell((r.sensitivity_categories || []).join(", ")));
      tr.appendChild(cell(r.strongest_score_type));
      tr.appendChild(cell(r.strongest_band));
      tr.appendChild(cell(scoreText(r.strongest_score)));
      tr.appendChild(cell(r.calibration_status));
      tr.appendChild(cell(r.exception_code));
      tr.appendChild(cell(r.reason_summary));
      findings.appendChild(tr);
      if (outcome) showOutcome(outcome, r);
    } else if (msg.event === "done") {
      stopRunning();  // settle any step still marked running
      status.textContent = failed ? "Stopped — unable to process." : "Completed.";
      const jobId = msg.result && msg.result.job_id;
      if (jobId) {
        const a = document.getElementById("to-workbook");
        a.href = "/jobs/" + jobId;
        a.style.display = "inline-block";
      }
      es.close();
    } else if (msg.event === "error") {
      failed = true;
      stopRunning(msg.message || "error");
      status.textContent = "Error: " + msg.message;
      es.close();
    }
  };
  es.onerror = () => {
    stopRunning();  // connection dropped → stop the animation
    if (status.textContent.indexOf("Processing") === 0) status.textContent = "Stream closed.";
    es.close();
  };
}

// ---- admin monitor (SSE) -----------------------------------------------
function initAdmin() {
  const root = document.getElementById("admin");
  if (!root) return;
  const es = new EventSource("/api/admin/stream");
  es.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (msg.event !== "summary") return;
    renderSummary(msg.summary);
    renderJobs(msg.jobs || []);
  };
  es.onerror = () => es.close();

  async function refreshRecords() {
    let data;
    try {
      data = await (await fetch("/api/admin/records")).json();
    } catch (e) {
      return;
    }
    renderRecords(data.records || []);
  }
  // Only the Workbook sub-page has the records table.
  const onWorkbook = !!document.getElementById("records-body");
  if (onWorkbook) {
    refreshRecords();
    setInterval(refreshRecords, 4000);
  }

  // Only the Evaluate sub-page has the eval table.
  if (document.getElementById("eval-body")) {
    async function refreshEval() {
      let data;
      try {
        data = await (await fetch("/api/admin/eval")).json();
      } catch (e) {
        return;
      }
      renderEval(data);
    }
    const filterEl = document.getElementById("eval-filter");
    if (filterEl) filterEl.addEventListener("change", renderEvalRows);
    refreshEval();
    setInterval(refreshEval, 5000);
  }

  root.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const id = btn.dataset.jobId;
    const action = btn.dataset.action;
    btn.disabled = true;
    try {
      await fetch("/api/jobs/" + encodeURIComponent(id) + "/" + action, { method: "POST" });
      toast(action + " requested for " + id, { ok: true });
      if (onWorkbook) refreshRecords();
    } catch (err) {
      toast(action + " failed: " + err);
    }
  });
}

let _recordsCache = [];
let _recordsBound = false;
function renderRecords(records) {
  _recordsCache = records;
  if (!_recordsBound) {
    _recordsBound = true;
    ["records-sort", "records-review-filter"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", applyRecordsView);
    });
    const body = document.getElementById("records-body");
    if (body) body.addEventListener("click", onAdjudicate);
  }
  applyRecordsView();
}
function applyRecordsView() {
  const body = document.getElementById("records-body");
  if (!body) return;
  const empty = document.getElementById("records-empty");
  const sortEl = document.getElementById("records-sort");
  const filterEl = document.getElementById("records-review-filter");
  const sortBy = sortEl ? sortEl.value : "uncertainty";
  const wantStatus = filterEl ? filterEl.value : "";

  let rows = _recordsCache.slice();
  if (wantStatus) rows = rows.filter((r) => (r.review_status || "pending") === wantStatus);
  if (sortBy === "uncertainty") {
    // least-confident first: ascending strongest_score, missing score treated as most certain
    const conf = (r) => (r.strongest_score == null ? Infinity : Number(r.strongest_score));
    rows.sort((a, b) => conf(a) - conf(b));
  } else {
    rows.sort((a, b) => String(a.source_id).localeCompare(String(b.source_id)));
  }
  body.textContent = "";
  if (empty) empty.hidden = _recordsCache.length > 0;
  const count = document.getElementById("records-count");
  if (count) count.textContent = rows.length + " shown";
  rows.forEach((r) => body.appendChild(recordRow(r)));
}
function recordRow(r) {
  const tr = document.createElement("tr");
  tr.appendChild(cell(r.source_id, "mono"));
  tr.appendChild(cell(r.content_type));
  tr.appendChild(chipCell(r.flag_status, r.flag_status));
  tr.appendChild(cell((r.sensitivity_categories || []).join(", ")));
  let strong = r.strongest_score_type || "—";
  if (r.strongest_band) strong += " · " + r.strongest_band;
  if (r.strongest_score != null) strong += " · " + Number(r.strongest_score).toFixed(1);
  tr.appendChild(cell(strong));
  tr.appendChild(cell(r.calibration_status));
  tr.appendChild(chipCell(r.review_status || "pending", r.review_status || "pending"));
  // adjudicate cell: rationale + accept/reject/needs-info
  const adj = document.createElement("td");
  const rat = document.createElement("input");
  rat.className = "rec-rationale";
  rat.placeholder = "rationale";
  rat.value = r.rationale || "";
  adj.appendChild(rat);
  [["accepted", "Accept"], ["rejected", "Reject"], ["needs_info", "Info"]].forEach(([st, label]) => {
    const b = document.createElement("button");
    b.className = "ghost";
    b.textContent = label;
    b.dataset.review = st;
    b.dataset.src = r.source_id;
    b.dataset.job = r.job_id || "";
    adj.appendChild(b);
  });
  tr.appendChild(adj);
  const td = document.createElement("td");
  const a = document.createElement("a");
  a.className = "btn ghost";
  a.href = "/jobs/" + encodeURIComponent(r.job_id);
  a.textContent = "results";
  td.appendChild(a);
  tr.appendChild(td);
  return tr;
}
async function onAdjudicate(e) {
  const btn = e.target.closest("button[data-review]");
  if (!btn) return;
  const cellRat = btn.parentElement.querySelector(".rec-rationale");
  const msg = document.getElementById("rec-review-msg");
  btn.disabled = true;
  try {
    const res = await fetch("/api/admin/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_id: btn.dataset.src,
        job_id: btn.dataset.job,
        status: btn.dataset.review,
        rationale: cellRat ? cellRat.value : "",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (msg) msg.textContent = data.error || "Could not save the decision.";
      btn.disabled = false;
      return;
    }
    // update the cached record so the view reflects the decision without a refetch
    const rec = _recordsCache.find((x) => x.source_id === btn.dataset.src);
    if (rec) {
      rec.review_status = data.review.status;
      rec.reviewer = data.review.reviewer;
      rec.rationale = data.review.rationale;
      rec.decided_at = data.review.decided_at;
    }
    if (msg) msg.textContent = "Recorded: " + btn.dataset.src + " → " + data.review.status;
    applyRecordsView();
  } catch (err) {
    if (msg) msg.textContent = "Could not save the decision.";
    btn.disabled = false;
  }
}

function setNum(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

// ---- evaluation (expected vs actual) -----------------------------------
let _evalReport = null;
function renderEval(report) {
  _evalReport = report;
  const f = report.flagging || {};
  const c = report.counts || {};
  setNum("e-precision", f.precision != null ? f.precision : "—");
  setNum("e-recall", f.recall != null ? f.recall : "—");
  setNum("e-f1", f.f1 != null ? f.f1 : "—");
  setNum("e-evaluated", (c.evaluated || 0) + " / " + (c.truth_records || 0));

  const bb = document.getElementById("eval-breakdown-body");
  if (bb) {
    bb.textContent = "";
    const bc = report.by_category || {};
    (report.categories || []).forEach((cat) => {
      const m = bc[cat];
      if (!m) return;
      const tr = document.createElement("tr");
      tr.appendChild(cell(cat));
      tr.appendChild(cell(m.precision));
      tr.appendChild(cell(m.recall));
      tr.appendChild(cell("F1 " + m.f1 + " · tp " + m.tp + " fp " + m.fp + " fn " + m.fn));
      bb.appendChild(tr);
    });
    const bs = report.by_scanned || {};
    [["scanned", "scanned"], ["born_digital", "born-digital"]].forEach(([k, label]) => {
      const s = bs[k];
      if (!s) return;
      const tr = document.createElement("tr");
      tr.appendChild(cell(label + " (flag recall)"));
      tr.appendChild(cell("—"));
      tr.appendChild(cell(s.recall));
      tr.appendChild(cell(s.found + " / " + s.expected + " expected flags found"));
      bb.appendChild(tr);
    });
    const cal = report.calibration || {};
    Object.keys(cal).forEach((status) => {
      const tr = document.createElement("tr");
      tr.appendChild(cell("calibration · " + status));
      tr.appendChild(cell("—"));
      tr.appendChild(cell("—"));
      tr.appendChild(cell(cal[status] + " rows"));
      bb.appendChild(tr);
    });
  }
  renderEvalRows();
}
function matchMark(v) {
  // null = unable_to_process (a processing failure, not a determination) — never a fake ✓/✗
  if (v == null) return "—";
  return v ? "✓" : "✗";
}
function renderEvalRows() {
  const body = document.getElementById("eval-body");
  if (!body || !_evalReport) return;
  const empty = document.getElementById("eval-empty");
  const count = document.getElementById("eval-count");
  const filterEl = document.getElementById("eval-filter");
  const onlyMismatch = filterEl && filterEl.value === "mismatch";
  let rows = _evalReport.rows || [];
  if (onlyMismatch) rows = rows.filter((r) => !r.flag_match || !r.categories_match);
  body.textContent = "";
  if (empty) empty.hidden = (_evalReport.rows || []).length > 0;
  if (count) count.textContent = rows.length + " shown";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.appendChild(cell(r.source_id, "mono"));
    tr.appendChild(cell(r.scanned ? "scan " + (r.scan_severity || "") : "digital"));
    tr.appendChild(chipCell(r.expected_flag_status, r.expected_flag_status));
    tr.appendChild(chipCell(r.actual_flag_status, r.actual_flag_status));
    tr.appendChild(cell(matchMark(r.flag_match)));
    tr.appendChild(cell((r.expected_categories || []).join(", ") || "—"));
    tr.appendChild(cell((r.actual_categories || []).join(", ") || "—"));
    tr.appendChild(cell(matchMark(r.categories_match)));
    body.appendChild(tr);
  });
}

function renderSummary(s) {
  setNum("m-authorised", s.authorised);
  setNum("m-processed", s.processed);
  setNum("m-flagged", s.flagged);
  setNum("m-not_flagged", s.not_flagged);
  setNum("m-unable", s.unable_to_process);
  setNum("m-in_progress", s.in_progress);
  setNum("m-remaining", s.remaining);
  setNum("m-pct", s.pct_complete + "%");
  const fill = document.getElementById("m-bar");
  if (fill) fill.style.width = Math.min(100, s.pct_complete) + "%";
}

function actionButton(label, action, jobId, className) {
  const b = document.createElement("button");
  b.className = className;
  b.textContent = label;
  b.dataset.action = action;
  b.dataset.jobId = jobId; // data-* is set as a property, never parsed as HTML
  return b;
}

function renderJobs(jobs) {
  const body = document.getElementById("jobs-body");
  if (!body) return;
  body.textContent = "";
  jobs.forEach((j) => {
    const done = j.progress_done || 0;
    const total = j.progress_total || 0;
    const active = j.status === "queued" || j.status === "running" || j.status === "retrying";
    const tr = document.createElement("tr");
    tr.appendChild(cell(j.job_id, "mono"));
    tr.appendChild(cell(j.request.job_type));
    tr.appendChild(chipCell(j.status));
    tr.appendChild(cell(done + " / " + total));
    tr.appendChild(cell(j.run_id, "mono"));

    const actions = document.createElement("td");
    const link = document.createElement("a");
    link.className = "btn ghost";
    link.href = "/jobs/" + encodeURIComponent(j.job_id);
    link.textContent = "results";
    actions.appendChild(link);
    actions.appendChild(document.createTextNode(" "));
    if (active) {
      actions.appendChild(actionButton("cancel", "cancel", j.job_id, "danger"));
      actions.appendChild(document.createTextNode(" "));
    }
    actions.appendChild(actionButton("retry", "retry-failed", j.job_id, "ghost"));
    tr.appendChild(actions);
    body.appendChild(tr);
  });
}

// ---- findings modal dialogs -------------------------------------------
const _MATCH_LABEL = "Matched content · PoC · re-read from source in-boundary, not stored";
function matchLabel() {
  const label = document.createElement("div");
  label.className = "fc-match-label";
  label.textContent = _MATCH_LABEL;
  return label;
}
function matchSkeleton() {
  // Placeholder shown immediately while the span is fetched (one read from source).
  const wrap = document.createElement("div");
  wrap.className = "fc-match loading";
  const bar = document.createElement("div");
  bar.className = "fc-match-skeleton";
  wrap.appendChild(matchLabel());
  wrap.appendChild(bar);
  return wrap;
}
function matchContent(span) {
  const wrap = document.createElement("div");
  wrap.className = "fc-match";
  const text = document.createElement("div");
  text.className = "fc-match-text mono";
  text.appendChild(document.createTextNode(span.char_pre || ""));
  const mark = document.createElement("mark");
  mark.textContent = span.char_match || "";
  text.appendChild(mark);
  text.appendChild(document.createTextNode(span.char_post || ""));
  wrap.appendChild(matchLabel());
  wrap.appendChild(text);
  return wrap;
}
async function revealDialog(dlg) {
  // Lazy, gated matched-content reveal: fetch ONE record's spans when its dialog opens.
  if (dlg.dataset.reveal !== "1" || dlg.dataset.loaded === "1") return;
  dlg.dataset.loaded = "1"; // once per dialog, even if the fetch fails
  const jobId = dlg.dataset.jobId;
  const sourceId = dlg.dataset.sourceId;
  if (!jobId || !sourceId) return;
  const slots = dlg.querySelectorAll(".fc-match-slot");
  slots.forEach((slot) => {
    slot.textContent = "";
    slot.appendChild(matchSkeleton()); // show the loading placeholder right away
  });
  let spans;
  try {
    const res = await fetch(
      "/api/jobs/" + encodeURIComponent(jobId) + "/reveal?source_id=" + encodeURIComponent(sourceId)
    );
    spans = (await res.json()).spans || [];
  } catch (e) {
    dlg.dataset.loaded = "0"; // allow a retry on reopen
    slots.forEach((slot) => (slot.textContent = "")); // clear placeholders on error
    return;
  }
  const byId = {};
  spans.forEach((s) => (byId[s.finding_id] = s));
  slots.forEach((slot) => {
    const span = byId[slot.dataset.findingId];
    slot.textContent = ""; // clear the skeleton
    if (span) slot.appendChild(matchContent(span));
  });
}
function initDialogs() {
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-dialog]");
    if (opener) {
      const dlg = document.getElementById(opener.dataset.dialog);
      if (dlg && typeof dlg.showModal === "function") {
        dlg.showModal();
        revealDialog(dlg);
      }
      return;
    }
    if (e.target.closest("[data-close]")) {
      const dlg = e.target.closest("dialog");
      if (dlg) dlg.close();
      return;
    }
    // Click on the backdrop (the dialog element itself) closes it.
    if (e.target.tagName === "DIALOG") e.target.close();
  });
}

// ---- navbar jobs notifications (global) --------------------------------
function renderNotifList(list, jobs) {
  list.textContent = "";
  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "notif-empty";
    empty.textContent = "No jobs yet.";
    list.appendChild(empty);
    return;
  }
  jobs.slice(0, 12).forEach((j) => {
    const row = document.createElement("a");
    row.className = "notif-item";
    row.href = "/jobs/" + encodeURIComponent(j.job_id);
    const top = document.createElement("div");
    top.className = "notif-item-top";
    const id = document.createElement("span");
    id.className = "mono";
    id.textContent = j.job_id;
    const chip = document.createElement("span");
    chip.className = "chip " + j.status;
    chip.textContent = j.status;
    top.appendChild(id);
    top.appendChild(chip);
    const sub = document.createElement("div");
    sub.className = "notif-item-sub muted";
    sub.textContent =
      (j.request && j.request.job_type ? j.request.job_type : "job") +
      " · " + (j.progress_done || 0) + "/" + (j.progress_total || 0);
    row.appendChild(top);
    row.appendChild(sub);
    list.appendChild(row);
  });
}

const NOTIF_ACTIVE = ["queued", "running", "retrying"];
const NOTIF_TERMINAL = ["completed", "failed", "cancelled"];
const NOTIF_DISMISS_KEY = "ws1_dismissed_jobs";

function loadDismissed() {
  try {
    return new Set(JSON.parse(localStorage.getItem(NOTIF_DISMISS_KEY) || "[]"));
  } catch (e) {
    return new Set();
  }
}
function saveDismissed(set) {
  try {
    localStorage.setItem(NOTIF_DISMISS_KEY, JSON.stringify([...set]));
  } catch (e) {
    /* storage unavailable — dismissal is best-effort */
  }
}

function initNotifications() {
  const btn = document.getElementById("notif-btn");
  const panel = document.getElementById("notif-panel");
  const list = document.getElementById("notif-list");
  const badge = document.getElementById("notif-badge");
  const clearBtn = document.getElementById("notif-clear");
  if (!btn || !panel || !list || !badge) return;

  const lastStatus = {};
  let seeded = false;
  let latestJobs = [];
  let dismissed = loadDismissed();

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.hidden = !panel.hidden;
  });
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== btn) panel.hidden = true;
  });

  // Clear only DISMISSES completed/failed/cancelled entries from the panel (client-side,
  // persisted). Running/queued jobs are never cleared, and nothing is deleted server-side.
  if (clearBtn) {
    clearBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      latestJobs.forEach((j) => {
        if (NOTIF_TERMINAL.includes(j.status)) dismissed.add(j.job_id);
      });
      saveDismissed(dismissed);
      render();
    });
  }

  function visible() {
    // Newest first; hide dismissed terminal jobs (active jobs always show).
    return latestJobs
      .filter((j) => !(dismissed.has(j.job_id) && NOTIF_TERMINAL.includes(j.status)))
      .slice()
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  }

  function render() {
    const shown = visible();
    renderNotifList(list, shown);
    const anyTerminalShown = shown.some((j) => NOTIF_TERMINAL.includes(j.status));
    if (clearBtn) clearBtn.disabled = !anyTerminalShown;
  }

  async function refresh() {
    let jobs;
    try {
      jobs = await (await fetch("/api/jobs?limit=20")).json();
    } catch (e) {
      return;
    }
    if (!Array.isArray(jobs)) return;
    latestJobs = jobs;
    // Bound the dismissed set to ids still present in the window.
    const present = new Set(jobs.map((j) => j.job_id));
    dismissed = new Set([...dismissed].filter((id) => present.has(id)));
    saveDismissed(dismissed);
    render();

    // Badge reflects ACTIVE (running/queued/retrying) jobs only — hidden when none.
    const active = jobs.filter((j) => NOTIF_ACTIVE.includes(j.status)).length;
    if (active > 0) {
      badge.textContent = String(active);
      badge.hidden = false;
    } else {
      badge.textContent = "";
      badge.hidden = true;
    }

    // Finish is announced by a transient toast (no persistent badge dot).
    jobs.forEach((j) => {
      const prev = lastStatus[j.job_id];
      if (seeded && prev && prev !== j.status && NOTIF_TERMINAL.includes(j.status)) {
        const kind = j.request && j.request.job_type ? j.request.job_type : "job";
        toast(kind + " " + j.job_id + " " + j.status, {
          ok: j.status === "completed",
          href: "/jobs/" + j.job_id,
          linkText: "View results →",
        });
      }
      lastStatus[j.job_id] = j.status;
    });
    seeded = true; // don't toast for jobs that were already terminal on first load
  }

  refresh();
  setInterval(refresh, 3000);
}

// ---- admin: custom recognizers ---------------------------------------
function initRecognizers() {
  const body = document.getElementById("rec-body");
  const form = document.getElementById("rec-form");
  if (!body || !form) return;
  const empty = document.getElementById("rec-empty");
  const msg = document.getElementById("rec-msg");

  function render(list) {
    body.textContent = "";
    if (empty) empty.hidden = list.length > 0;
    list.forEach((r) => {
      const tr = document.createElement("tr");
      tr.appendChild(cell(r.name, "mono"));
      tr.appendChild(cell(r.supported_entity, "mono"));
      tr.appendChild(chipCell(r.category, "cat"));
      tr.appendChild(cell(r.regex, "mono"));
      tr.appendChild(cell(scoreText(r.score)));
      tr.appendChild(cell((r.context || []).join(", ") || "—"));
      tr.appendChild(cell(r.deterministic ? "deterministic" : "classifier"));
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "ghost";
      btn.textContent = "Delete";
      btn.dataset.del = r.name;
      td.appendChild(btn);
      tr.appendChild(td);
      body.appendChild(tr);
    });
  }
  async function load() {
    try {
      const res = await fetch("/api/admin/recognizers");
      render((await res.json()).recognizers || []);
    } catch (e) {
      /* leave the table as-is on a transient error */
    }
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (msg) msg.textContent = "";
    const fd = new FormData(form);
    const context = String(fd.get("context") || "")
      .split(",").map((s) => s.trim()).filter(Boolean);
    const payload = {
      name: fd.get("name"),
      supported_entity: fd.get("supported_entity"),
      category: fd.get("category"),
      regex: fd.get("regex"),
      score: parseFloat(fd.get("score")) || 0.4,
      context: context,
      deterministic: fd.get("deterministic") === "on",
    };
    try {
      const res = await fetch("/api/admin/recognizers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        if (msg) msg.textContent = data.error || "Invalid recognizer (check the regex).";
        return;
      }
      form.reset();
      if (msg) msg.textContent = "Added — applies to the next run.";
      render(data.recognizers || []);
    } catch (err) {
      if (msg) msg.textContent = "Could not save the recognizer.";
    }
  });
  body.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-del]");
    if (!btn) return;
    const res = await fetch("/api/admin/recognizers/" + encodeURIComponent(btn.dataset.del), {
      method: "DELETE",
    });
    render((await res.json()).recognizers || []);
  });
  load();
}

document.addEventListener("DOMContentLoaded", () => {
  initWs1();
  initLive();
  initAdmin();
  initDialogs();
  initNotifications();
  initRecognizers();
});
