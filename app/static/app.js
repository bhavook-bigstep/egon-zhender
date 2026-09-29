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
          toast("Batch queued (" + ids.length + " items).", {
            ok: true,
            href: "/jobs/" + job.job_id,
            linkText: "View results →",
          });
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

// ---- single interactive live view (SSE) --------------------------------
function initLive() {
  const root = document.getElementById("live");
  if (!root) return;
  const sourceId = root.dataset.sourceId;
  const timeline = document.getElementById("timeline");
  const findings = document.getElementById("findings-body");
  const status = document.getElementById("live-status");

  const es = new EventSource("/api/interactive/stream?source_id=" + encodeURIComponent(sourceId));
  es.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (msg.event === "stage") {
      const li = document.createElement("li");
      li.className = msg.exception_code ? "failed" : "done";
      li.textContent =
        msg.stage + " — " + msg.outcome + (msg.exception_code ? " (" + msg.exception_code + ")" : "");
      timeline.appendChild(li);
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

  root.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const id = btn.dataset.jobId;
    const action = btn.dataset.action;
    btn.disabled = true;
    try {
      await fetch("/api/jobs/" + encodeURIComponent(id) + "/" + action, { method: "POST" });
      toast(action + " requested for " + id, { ok: true });
    } catch (err) {
      toast(action + " failed: " + err);
    }
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

document.addEventListener("DOMContentLoaded", () => {
  initWs1();
  initLive();
  initAdmin();
  initDialogs();
});
