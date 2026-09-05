/* runs.js — 任务页：队列 + 实时进度 + 历史（ETA/重试） */
import { $, $$, api, toast, goto } from "./app.js";
import { t, tf } from "./i18n.js";
import { uiConfirm } from "./ui.js";

export function initRuns() {
  $("#q-interrupt").addEventListener("click", async () => {
    const r = await api("/api/interrupt", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
  });
  $("#q-clear").addEventListener("click", async () => {
    if (!(await uiConfirm(t("misc.confirm.clear.queue")))) return;
    const r = await api("/api/clear_queue", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    refresh();
  });
  refresh();
  setInterval(refresh, 3000);
}

/* 行内进度：SSE progress 按 prompt_id 记账，渲染到执行中的行 */
const rowProgress = {};   // pid -> {value, max, node}

export function runsOnSSE(ev) {
  if (!$("#view-runs").classList.contains("active")) return;
  const t = ev.type, d = ev.data || {};
  if (t === "progress") {
    if (d.prompt_id) rowProgress[d.prompt_id] = { value: d.value, max: d.max, node: d.node };
    $("#progress-panel").hidden = false;
    const pct = d.max ? Math.round((d.value / d.max) * 100) : 0;
    $("#prog-node").textContent = tf("runs.node.sampling", d.node ?? "");
    $("#prog-pct").textContent = `${d.value}/${d.max}（${pct}%）`;
    $("#prog-fill").style.width = pct + "%";
  }
  if (t === "executing" && d.node != null) {
    $("#progress-panel").hidden = false;
    $("#prog-node").textContent = tf("runs.node.doing", d.node);
  }
  if (t === "execution_start" || t === "status") refresh();
  if (t === "execution_success" || t === "execution_error" || t === "execution_interrupted") {
    delete rowProgress[d.data?.prompt_id];
    setTimeout(refresh, 800);
  }
}

const isVideoRun = (name) => /H3|视频|video/i.test(name || "");
const estMin = (name) => (isVideoRun(name) ? 8.5 : 2);
function elapsedMin(submitted) {
  try {
    const [d, t] = submitted.split(" ");
    const [Y, M, D] = d.split("-").map(Number);
    const [hh, mm, ss] = t.split(":").map(Number);
    return (Date.now() - new Date(Y, M - 1, D, hh, mm, ss).getTime()) / 60000;
  } catch { return 0; }
}
const fmtEta = (m) => m < 1 ? t("runs.eta.lt1") : tf("runs.eta.min", Math.ceil(m));

async function refresh() {
  if (!$("#view-runs").classList.contains("active")) return;
  let q = null;
  try { q = (await api("/api/queue")).queue; } catch { return; }
  if (!q) return;
  const pend = q.queue_pending || [], run = q.queue_running || [];
  $("#q-pending-n").textContent = pend.length;
  $("#q-running-n").textContent = run.length;
  const fmtQ = (arr) => arr.length
    ? arr.map(([num, info]) => {
        const nodes = Object.keys(info?.prompt?.[0] || {}).length;
        return `<div class="q-item"><span>${tf("runs.job.n", num)}</span><span class="muted">${nodes}${t("unit.nodes")}</span></div>`;
      }).join("")
    : `<div class="muted">${t("empty.paren")}</div>`;
  $("#q-pending").innerHTML = fmtQ(pend);
  $("#q-running").innerHTML = fmtQ(run);
  renderHistory();
}

async function renderHistory() {
  const r = await api("/api/history?limit=25");
  if (!r.ok) { $("#runs-list").innerHTML = `<div class="card pad muted">${t("empty.runs.offline")}</div>`; return; }
  const runs = await api("/api/runs");   // 带 submitted/graph 快照
  const byPid = runs.ok ? Object.fromEntries(runs.runs.map((x) => [x.prompt_id, x])) : {};
  const box = $("#runs-list");
  box.innerHTML = "";
  if (!r.history.length) { box.innerHTML = `<div class="card pad muted">${t("empty.runs")}</div>`; return; }
  const wrap = document.createElement("div");
  wrap.className = "card";
  for (const h of r.history) {
    const row = document.createElement("div");
    row.className = "run-row";
    const info = byPid[h.prompt_id] || {};
    const name = info.name || h.name || h.prompt_id.slice(0, 8);
    const st = h.status === "success" || h.completed ? "success" : (h.status === "error" ? "error" : (h.status === "executing" ? "running" : "queued"));
    const stTxt = { success: "✓ " + t("status.success"), error: "✗ " + t("status.error"), running: t("status.running"), queued: t("status.queued") }[st] || h.status;
    let meta = h.prompt_id.slice(0, 8);
    if (st === "running" || st === "queued") {
      const el = elapsedMin(info.submitted || "");
      meta += tf("runs.elapsed", el < 1 ? "<1" : Math.floor(el), fmtEta(el + estMin(name) * (st === "queued" ? 1 : 0.5)));
    } else if (info.submitted) {
      meta += " · " + info.submitted.slice(5, 16);
    }
    const outs = (h.outputs || []).map((o) => {
      const rel = (o.subfolder ? o.subfolder + "/" : "") + o.filename;
      const qs = `filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder)}&type=${o.type}`;
      const src = o.type === "output" ? mediaUrl(rel) : "/api/comfyview?" + qs;
      const tSrc = (o.type === "output" && /\.(mp4|webm|gif|mov|mkv)$/i.test(o.filename)) ? mediaUrl(rel, { thumb: "1" }) : src;
      return `<img src="${tSrc}" loading="lazy" title="${esc(o.filename)}" data-full="${src}">`;
    }).join("");
    const retryable = info.graph ? `<button class="btn ghost run-retry" data-pid="${h.prompt_id}">↻ ${t("act.retry")}</button>` : "";
    const prog = rowProgress[h.prompt_id];
    const progHtml = (st === "running" && prog?.max)
      ? `<div class="row-progress"><i style="width:${Math.round(prog.value / prog.max * 100)}%"></i></div>` : "";
    row.innerHTML = `<span class="run-status ${st}">${stTxt}</span>
      <span class="run-name">${esc(name)}${progHtml}</span>
      <span class="run-meta">${esc(meta)}</span>
      ${retryable}
      <div class="run-outs">${outs}</div>`;
    row.querySelectorAll("img").forEach((im) => im.addEventListener("click", () => window.open(im.dataset.full, "_blank")));
    row.querySelector(".run-retry")?.addEventListener("click", async () => {
      const rr = await api("/api/rerun", { method: "POST", body: { prompt_id: h.prompt_id } });
      rr.ok ? toast(rr.msg, "ok") : toast(rr.msg || rr.error, "err");
    });
    wrap.appendChild(row);
  }
  box.appendChild(wrap);
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
