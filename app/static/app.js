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
function renderStep(container, msg, index) {
  if (index > 1) {
    const arrow = document.createElement("div");
    arrow.className = "step-arrow";
    arrow.textContent = "→";
    container.appendChild(arrow);
  }
  const node = document.createElement("div");
  node.className = "step-node " + (msg.exception_code ? "failed" : "done");
  node.setAttribute("role", "button");
  node.tabIndex = 0;
  const no = document.createElement("span");
  no.className = "step-no";
  no.textContent = "STEP " + index;
  const name = document.createElement("span");
  name.className = "step-name";
  name.textContent = STEP_LABELS[msg.stage] || msg.stage;
  const out = document.createElement("span");
  out.className = "chip" + (msg.exception_code ? " unable_to_process" : "");
  out.textContent = msg.exception_code || msg.outcome;
  node.appendChild(no);
  node.appendChild(name);
  node.appendChild(out);
  node.addEventListener("click", () => openStepDialog(msg, index));
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openStepDialog(msg, index);
    }
  });
  container.appendChild(node);
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
  const status = document.getElementById("live-status");

  let stepNo = 0;
  const es = new EventSource("/api/interactive/stream?source_id=" + encodeURIComponent(sourceId));
  es.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (msg.event === "stage") {
      stepNo += 1;
      renderStep(timeline, msg, stepNo);
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
    } else if (msg.event === "done") {
      status.textContent = "Completed.";
      const jobId = msg.result && msg.result.job_id;
      if (jobId) {
        const a = document.getElementById("to-workbook");
        a.href = "/jobs/" + jobId;
        a.style.display = "inline-block";
      }
      es.close();
    } else if (msg.event === "error") {
      status.textContent = "Error: " + msg.message;
      es.close();
    }
  };
  es.onerror = () => {
    status.textContent = "Stream closed.";
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

function renderRecords(records) {
  const body = document.getElementById("records-body");
  const empty = document.getElementById("records-empty");
  if (!body) return;
  body.textContent = "";
  if (empty) empty.hidden = records.length > 0;
  const count = document.getElementById("records-count");
  if (count) count.textContent = records.length + " records";
  records.forEach((r) => {
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
    const td = document.createElement("td");
    const a = document.createElement("a");
    a.className = "btn ghost";
    a.href = "/jobs/" + encodeURIComponent(r.job_id);
    a.textContent = "results";
    td.appendChild(a);
    tr.appendChild(td);
    body.appendChild(tr);
  });
}

function setNum(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
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
function initDialogs() {
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-dialog]");
    if (opener) {
      const dlg = document.getElementById(opener.dataset.dialog);
      if (dlg && typeof dlg.showModal === "function") dlg.showModal();
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

document.addEventListener("DOMContentLoaded", () => {
  initWs1();
  initLive();
  initAdmin();
  initDialogs();
  initNotifications();
});
