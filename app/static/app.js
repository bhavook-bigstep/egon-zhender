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
  const body = document.getElementById("rows");

  // Selection survives page navigation: the source browser pages server-side
  // (one PAGE_SIZE window per fetch, so the full corpus never loads at once),
  // while chosen ids live in a Set that spans pages.
  const selectedIds = new Set();
  let _srcPage = 1;
  let _srcTotal = 0;
  let _pageItems = [];

  function selected() {
    return Array.from(selectedIds);
  }
  function refreshCount() {
    const label = document.getElementById("selcount");
    if (label) label.textContent = selectedIds.size + " selected";
  }
  function syncSelectAll() {
    const selAll = document.getElementById("select-all");
    if (selAll)
      selAll.checked = _pageItems.length > 0 && _pageItems.every((e) => selectedIds.has(e.source_id));
  }

  function drawRows() {
    if (!body) return;
    body.textContent = "";
    _pageItems.forEach((e) => {
      const tr = document.createElement("tr");
      const selTd = document.createElement("td");
      selTd.className = "rowsel";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "rowcheck";
      cb.value = e.source_id;
      cb.checked = selectedIds.has(e.source_id);
      selTd.appendChild(cb);
      tr.appendChild(selTd);
      tr.appendChild(cell(e.source_id, "mono"));
      tr.appendChild(cell(e.content_type));
      tr.appendChild(cell(e.author));
      tr.appendChild(cell(e.datetime));
      tr.appendChild(cell(e.linked_executive));
      tr.appendChild(cell(e.linked_project));
      body.appendChild(tr);
    });
    syncSelectAll();
    renderPager(document.getElementById("rows-pager"), _srcPage, _srcTotal, (p) => loadPage(p));
  }

  async function loadPage(page) {
    const offset = (page - 1) * PAGE_SIZE;
    let data;
    try {
      data = await (
        await fetch("/api/source/manifest?offset=" + offset + "&limit=" + PAGE_SIZE)
      ).json();
    } catch (err) {
      toast("Could not load the source list: " + err);
      return;
    }
    _srcTotal = data.total || 0;
    _srcPage = page;
    _pageItems = data.items || [];
    drawRows();
  }

  // Checkbox state lives in the Set; delegation covers rows re-rendered per page.
  if (body)
    body.addEventListener("change", (e) => {
      if (!(e.target.classList && e.target.classList.contains("rowcheck"))) return;
      if (e.target.checked) selectedIds.add(e.target.value);
      else selectedIds.delete(e.target.value);
      refreshCount();
      syncSelectAll();
    });
  const selAllEl = document.getElementById("select-all");
  if (selAllEl)
    selAllEl.addEventListener("change", (e) => {
      _pageItems.forEach((it) => {
        if (e.target.checked) selectedIds.add(it.source_id);
        else selectedIds.delete(it.source_id);
      });
      if (body) body.querySelectorAll(".rowcheck").forEach((c) => (c.checked = e.target.checked));
      refreshCount();
    });

  async function submitBatch(ids) {
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_type: "batch", config_version: configVersion, source_ids: ids }),
      });
      const job = await res.json();
      if (job.status === "failed") {
        toast("Rejected: " + (job.exception || "unknown error"), { sticky: true });
        return false;
      }
      toast("Queued (" + ids.length + " item" + (ids.length === 1 ? "" : "s") + ").", { ok: true });
      batchNotification(job.job_id, ids.length);
      return true;
    } catch (err) {
      toast("Submit failed: " + err);
      return false;
    }
  }

  // Smart run: 0 → prompt; >1 → batch straight away; exactly 1 → live-or-queue dialog.
  const run = document.getElementById("run-selected");
  if (run)
    run.addEventListener("click", async () => {
      const ids = selected();
      if (ids.length === 0) {
        toast("Select at least one item.");
        return;
      }
      if (ids.length > 1) {
        run.disabled = true;
        if (await submitBatch(ids)) setTimeout(() => (window.location.href = "/jobs"), 600);
        run.disabled = false;
        return;
      }
      const dlg = document.getElementById("run-dialog");
      const idLabel = document.getElementById("run-dialog-id");
      if (idLabel) idLabel.textContent = ids[0];
      const live = document.getElementById("run-live");
      const queue = document.getElementById("run-queue");
      if (live)
        live.onclick = () => {
          window.location.href = "/ws1/live?source_id=" + encodeURIComponent(ids[0]);
        };
      if (queue)
        queue.onclick = async () => {
          queue.disabled = true;
          if (await submitBatch(ids)) setTimeout(() => (window.location.href = "/jobs"), 600);
          queue.disabled = false;
        };
      if (dlg && typeof dlg.showModal === "function") dlg.showModal();
    });

  loadPage(1);
  refreshCount();
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

// ---- shared page-based pagination -------------------------------------
const PAGE_SIZE = 20;
function pageWindow(page, pages) {
  // e.g. [1, "…", 4, 5, 6, "…", 20]
  const want = new Set([1, pages, page, page - 1, page + 1]);
  const nums = [...want].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const win = [];
  let prev = 0;
  nums.forEach((n) => {
    if (n - prev > 1) win.push("…");
    win.push(n);
    prev = n;
  });
  return win;
}
function renderPager(el, page, total, onGo) {
  if (!el) return;
  el.textContent = "";
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  page = Math.min(Math.max(1, page), pages);
  const info = document.createElement("span");
  info.className = "pager-info";
  const start = total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const end = Math.min(page * PAGE_SIZE, total);
  info.textContent = start + "–" + end + " of " + total;
  el.appendChild(info);
  if (pages <= 1) return;
  const nav = document.createElement("div");
  nav.className = "pager-nav";
  const mk = (label, target, disabled, active) => {
    const b = document.createElement("button");
    b.className = "pager-btn" + (active ? " active" : "");
    b.textContent = label;
    b.disabled = !!disabled;
    if (!disabled && !active) b.addEventListener("click", () => onGo(target));
    return b;
  };
  nav.appendChild(mk("‹", page - 1, page <= 1));
  pageWindow(page, pages).forEach((p) => {
    if (p === "…") {
      const gap = document.createElement("span");
      gap.className = "pager-gap";
      gap.textContent = "…";
      nav.appendChild(gap);
    } else {
      nav.appendChild(mk(String(p), p, false, p === page));
    }
  });
  nav.appendChild(mk("›", page + 1, page >= pages));
  el.appendChild(nav);
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
    const scope = (document.getElementById("admin") || {}).dataset;
    const job = scope && scope.jobScope ? scope.jobScope : "";
    const url = "/api/admin/records" + (job ? "?job=" + encodeURIComponent(job) : "");
    let data;
    try {
      data = await (await fetch(url)).json();
    } catch (e) {
      return;
    }
    renderRecords(data.records || []);
  }
  // Only the Records hub has a records table (#records-body) and auto-polls it. The Jobs
  // page's results overlay uses its own #job-records-body, filled on demand per job.
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
    if (filterEl)
      filterEl.addEventListener("change", () => {
        _evalPage = 1;
        renderEvalRows();
      });
    refreshEval();
    setInterval(refreshEval, 5000);
  }

  // Open a job's produced results in an overlay on the Jobs page (no navigation away).
  root.addEventListener("click", (e) => {
    const rbtn = e.target.closest("button[data-job-results]");
    if (rbtn) openJobDialog(rbtn.dataset.jobResults);
  });

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

// The Jobs results overlay: a READ-ONLY view of the rows one run produced (scoped,
// content-free), with per-record detail. No adjudication here — approval lives only on
// the Records hub, over the latest version of each record.
let _jobRecords = [];
let _jobRecordsJob = "";
let _jobRecordsPage = 1;
let _jobRecordsBound = false;
async function openJobDialog(jobId) {
  const dlg = document.getElementById("job-dialog");
  if (!dlg || !jobId) return;
  _jobRecordsJob = jobId;
  const idLabel = document.getElementById("job-dialog-id");
  if (idLabel) idLabel.textContent = jobId;
  if (!_jobRecordsBound) {
    _jobRecordsBound = true;
    const sortEl = document.getElementById("job-records-sort");
    if (sortEl)
      sortEl.addEventListener("change", () => {
        _jobRecordsPage = 1;
        applyJobRecordsView();
      });
    const body = document.getElementById("job-records-body");
    if (body)
      body.addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-details]");
        if (btn) openRecordDrawer(btn.dataset.details, btn.dataset.job);
      });
  }
  _jobRecords = [];
  _jobRecordsPage = 1;
  applyJobRecordsView();
  const count = document.getElementById("job-records-count");
  if (count) count.textContent = "loading…";
  if (typeof dlg.showModal === "function") dlg.showModal();

  let data;
  try {
    data = await (
      await fetch("/api/admin/records?job=" + encodeURIComponent(jobId))
    ).json();
  } catch (e) {
    if (count) count.textContent = "could not load this run's records";
    return;
  }
  _jobRecords = data.records || [];
  applyJobRecordsView();
}
function applyJobRecordsView() {
  const body = document.getElementById("job-records-body");
  if (!body) return;
  const sortEl = document.getElementById("job-records-sort");
  const sortBy = sortEl ? sortEl.value : "uncertainty";
  let rows = _jobRecords.slice();
  if (sortBy === "uncertainty") {
    const conf = (r) => (r.strongest_score == null ? Infinity : Number(r.strongest_score));
    rows.sort((a, b) => conf(a) - conf(b));
  } else {
    rows.sort((a, b) => String(a.source_id).localeCompare(String(b.source_id)));
  }
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (_jobRecordsPage > pages) _jobRecordsPage = pages;
  const pageRows = rows.slice((_jobRecordsPage - 1) * PAGE_SIZE, _jobRecordsPage * PAGE_SIZE);
  body.textContent = "";
  const empty = document.getElementById("job-records-empty");
  if (empty) empty.hidden = _jobRecords.length > 0;
  const count = document.getElementById("job-records-count");
  if (count) count.textContent = total + " record" + (total === 1 ? "" : "s");
  pageRows.forEach((r) => body.appendChild(jobRecordRow(r)));
  renderPager(document.getElementById("job-records-pager"), _jobRecordsPage, total, (p) => {
    _jobRecordsPage = p;
    applyJobRecordsView();
  });
}
function jobRecordRow(r) {
  const tr = document.createElement("tr");
  tr.appendChild(cell(r.source_id, "mono"));
  tr.appendChild(cell(r.content_type));
  tr.appendChild(chipCell(r.flag_status, r.flag_status));
  tr.appendChild(cell((r.sensitivity_categories || []).join(", ")));
  // Strongest: stack score_type / band / score on their own lines so the column stays narrow.
  const strongTd = document.createElement("td");
  strongTd.className = "strong-cell";
  const parts = [r.strongest_score_type || "—"];
  if (r.strongest_band) parts.push(r.strongest_band);
  if (r.strongest_score != null) parts.push(Number(r.strongest_score).toFixed(1));
  parts.forEach((p) => {
    const line = document.createElement("div");
    line.textContent = p;
    strongTd.appendChild(line);
  });
  tr.appendChild(strongTd);
  tr.appendChild(cell(r.calibration_status));
  const td = document.createElement("td");
  const btn = document.createElement("button");
  btn.className = "ghost";
  btn.textContent = "Details";
  btn.dataset.details = r.source_id;
  btn.dataset.job = r.job_id || _jobRecordsJob;
  td.appendChild(btn);
  tr.appendChild(td);
  return tr;
}

let _recordsCache = [];
let _recordsBound = false;
let _recordsPage = 1;
function renderRecords(records) {
  _recordsCache = records;
  if (!_recordsBound) {
    _recordsBound = true;
    ["records-sort", "records-review-filter"].forEach((id) => {
      const el = document.getElementById(id);
      if (el)
        el.addEventListener("change", () => {
          _recordsPage = 1;  // filter/sort resets to the first page
          applyRecordsView();
        });
    });
    const body = document.getElementById("records-body");
    if (body) {
      body.addEventListener("click", onAdjudicate);
      body.addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-details]");
        if (btn) openRecordDrawer(btn.dataset.details, btn.dataset.job);
      });
    }
  }
  applyRecordsView();
}
// Master-detail drawer: findings (content-free) + gated reveal + provenance for one record.
async function openRecordDrawer(sourceId, jobId) {
  const dlg = document.getElementById("record-dialog");
  if (!dlg) return;
  const reveal = ((document.getElementById("admin") || {}).dataset || {}).reveal === "1";
  dlg.textContent = "";
  dlg.dataset.jobId = jobId;
  dlg.dataset.sourceId = sourceId;
  dlg.dataset.reveal = reveal ? "1" : "0";
  dlg.dataset.loaded = "0";

  const head = document.createElement("div");
  head.className = "dialog-head";
  const title = document.createElement("strong");
  title.className = "mono";
  title.textContent = sourceId;
  const close = document.createElement("button");
  close.className = "ghost icon";
  close.setAttribute("data-close", "");
  close.setAttribute("aria-label", "Close");
  close.textContent = "✕";
  head.appendChild(title);
  head.appendChild(close);
  dlg.appendChild(head);

  const body = document.createElement("div");
  body.className = "dialog-body";
  const status = document.createElement("p");
  status.className = "muted";
  status.textContent = "Loading findings…";
  body.appendChild(status);
  dlg.appendChild(body);
  if (typeof dlg.showModal === "function") dlg.showModal();

  let findings;
  try {
    const res = await fetch(
      "/api/records/" + encodeURIComponent(sourceId) + "/findings?job=" + encodeURIComponent(jobId)
    );
    findings = (await res.json()).findings || [];
  } catch (e) {
    status.textContent = "Could not load findings.";
    return;
  }
  status.remove();
  if (!findings.length) {
    const none = document.createElement("p");
    none.className = "muted";
    none.textContent = "No findings for this record.";
    body.appendChild(none);
    return;
  }
  findings.forEach((f) => body.appendChild(buildFindingCard(f, reveal)));
  if (reveal) revealDialog(dlg);  // fills the fc-match-slot(s) via the gated reveal endpoint
}
function buildFindingCard(f, reveal) {
  const card = document.createElement("div");
  card.className = "finding-card";
  const fh = document.createElement("div");
  fh.className = "fc-head";
  const catChip = document.createElement("span");
  catChip.className = "chip cat";
  catChip.textContent = f.category;
  fh.appendChild(catChip);
  const kind = document.createElement("span");
  kind.className = "chip" + (f.routing_only ? " similarity" : "");
  kind.textContent = f.routing_only ? "routing only" : "flag-driving";
  fh.appendChild(kind);
  if (f.method) {
    // Which evaluator flagged it (Presidio / Semantic / LLM / rule) — the reviewer's "who".
    const by = document.createElement("span");
    by.className = "chip by";
    by.textContent = "by " + f.method;
    fh.appendChild(by);
  }
  const score = document.createElement("span");
  score.className = "fc-score";
  if (f.score == null) score.textContent = "deterministic match";
  else score.textContent = Number(f.score).toFixed(1) + (f.band ? " · " + f.band : "");
  fh.appendChild(score);
  card.appendChild(fh);
  const reason = document.createElement("div");
  reason.className = "fc-reason";
  reason.textContent = f.reason_text || "";
  card.appendChild(reason);
  // Matched content: only for findings with a specific span. A semantic routing signal is
  // document-level — showing the whole page as "matched content" is noise, so skip it.
  if (reveal && !f.routing_only) {
    const slot = document.createElement("div");
    slot.className = "fc-match-slot";
    slot.dataset.findingId = f.finding_id;
    card.appendChild(slot);
  } else if (f.routing_only) {
    const note = document.createElement("div");
    note.className = "fc-routing-note";
    note.textContent = "Document-level routing signal — no specific span (it only decides which categories reach the model).";
    card.appendChild(note);
  }
  const loc = document.createElement("div");
  loc.className = "fc-meta";
  const dl = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = "Evidence location";
  const dd = document.createElement("dd");
  dd.className = "mono";
  dd.textContent = f.evidence_str || "—";
  dl.appendChild(dt);
  dl.appendChild(dd);
  loc.appendChild(dl);
  card.appendChild(loc);
  return card;
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
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (_recordsPage > pages) _recordsPage = pages;
  const pageRows = rows.slice((_recordsPage - 1) * PAGE_SIZE, _recordsPage * PAGE_SIZE);
  body.textContent = "";
  if (empty) empty.hidden = _recordsCache.length > 0;
  const count = document.getElementById("records-count");
  if (count) count.textContent = total + " total";
  pageRows.forEach((r) => body.appendChild(recordRow(r)));
  renderPager(document.getElementById("records-pager"), _recordsPage, total, (p) => {
    _recordsPage = p;
    applyRecordsView();
  });
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
  adj.className = "adj-cell";
  const rat = document.createElement("input");
  rat.className = "rec-rationale";
  rat.placeholder = "rationale (optional)";
  rat.value = r.rationale || "";
  adj.appendChild(rat);
  const adjBtns = document.createElement("div");
  adjBtns.className = "adj-buttons";
  [["accepted", "Accept"], ["rejected", "Reject"], ["needs_info", "Info"]].forEach(([st, label]) => {
    const b = document.createElement("button");
    b.className = "ghost";
    b.textContent = label;
    b.dataset.review = st;
    b.dataset.src = r.source_id;
    b.dataset.job = r.job_id || "";
    b.dataset.run = r.run_id || "";  // ties the decision to the reviewed version
    adjBtns.appendChild(b);
  });
  adj.appendChild(adjBtns);
  tr.appendChild(adj);
  const td = document.createElement("td");
  const btn = document.createElement("button");
  btn.className = "ghost";
  btn.textContent = "Details";
  btn.dataset.details = r.source_id;
  btn.dataset.job = r.job_id || "";
  td.appendChild(btn);
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
        run_id: btn.dataset.run || "",
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
let _evalPage = 1;
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
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (_evalPage > pages) _evalPage = pages;
  const pageRows = rows.slice((_evalPage - 1) * PAGE_SIZE, _evalPage * PAGE_SIZE);
  body.textContent = "";
  if (empty) empty.hidden = (_evalReport.rows || []).length > 0;
  if (count) count.textContent = total + " total";
  pageRows.forEach((r) => {
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
  renderPager(document.getElementById("eval-pager"), _evalPage, total, (p) => {
    _evalPage = p;
    renderEvalRows();
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

let _jobsCache = [];
let _jobsPage = 1;
function renderJobs(jobs) {
  const body = document.getElementById("jobs-body");
  if (!body) return;
  _jobsCache = jobs;
  drawJobs();
}
function drawJobs() {
  const body = document.getElementById("jobs-body");
  if (!body) return;
  const jobs = _jobsCache;
  const total = jobs.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (_jobsPage > pages) _jobsPage = pages;
  const pageRows = jobs.slice((_jobsPage - 1) * PAGE_SIZE, _jobsPage * PAGE_SIZE);
  body.textContent = "";
  pageRows.forEach((j) => {
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
    const results = document.createElement("button");
    results.className = "btn ghost";
    results.textContent = "results";
    results.dataset.jobResults = j.job_id;  // opens the results overlay (no navigation)
    actions.appendChild(results);
    actions.appendChild(document.createTextNode(" "));
    if (active) {
      actions.appendChild(actionButton("cancel", "cancel", j.job_id, "danger"));
      actions.appendChild(document.createTextNode(" "));
    }
    actions.appendChild(actionButton("retry", "retry-failed", j.job_id, "ghost"));
    tr.appendChild(actions);
    body.appendChild(tr);
  });
  renderPager(document.getElementById("jobs-pager"), _jobsPage, total, (p) => {
    _jobsPage = p;
    drawJobs();
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
      let kind = r.deterministic ? "deterministic" : "classifier";
      if (r.validator) kind = "checksum · " + r.validator;  // checksum → deterministic on pass
      tr.appendChild(cell(kind));
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
  // Reveal the weighted-modulus parameter panel only when that checksum is chosen.
  const validatorSel = document.getElementById("rec-validator");
  const wmPanel = document.getElementById("wm-params");
  if (validatorSel && wmPanel)
    validatorSel.addEventListener("change", () => {
      wmPanel.hidden = validatorSel.value !== "weighted_modulus";
    });
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
      validator: fd.get("validator") || null,
      checksum: null,
    };
    if (payload.validator === "weighted_modulus") {
      const weights = String(fd.get("wm_weights") || "")
        .split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n));
      payload.checksum = {
        mode: fd.get("wm_mode") || "weighted_sum",
        modulus: parseInt(fd.get("wm_modulus"), 10) || 0,
        expect: parseInt(fd.get("wm_expect"), 10) || 0,
        alphabet: fd.get("wm_alphabet") || "digits",
        weights: weights,
        align: fd.get("wm_align") || "left",
        rotate: parseInt(fd.get("wm_rotate"), 10) || 0,
      };
    }
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
      if (wmPanel) wmPanel.hidden = true;  // reset() doesn't fire change
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

// ---- sidebar drawer (mobile) ------------------------------------------
function initNav() {
  const toggle = document.getElementById("nav-toggle");
  const scrim = document.getElementById("nav-scrim");
  if (!toggle) return;
  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    if (scrim) scrim.hidden = !open;
  };
  toggle.addEventListener("click", () =>
    setOpen(!document.body.classList.contains("nav-open"))
  );
  if (scrim) scrim.addEventListener("click", () => setOpen(false));
  document
    .querySelectorAll(".sidenav-nav a")
    .forEach((a) => a.addEventListener("click", () => setOpen(false)));
}

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  initWs1();
  initLive();
  initAdmin();
  initDialogs();
  initNotifications();
  initRecognizers();
});
