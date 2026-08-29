/* runs.js — 任务页：队列 + 实时进度 + 历史（ETA/重试） */
import { $, $$, api, toast, goto } from "./app.js";

export function initRuns() {
  $("#q-interrupt").addEventListener("click", async () => {
    const r = await api("/api/interrupt", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
  });
  $("#q-clear").addEventListener("click", async () => {
    if (!confirm("清空整个排队队列？（不影响正在执行的）")) return;
    const r = await api("/api/clear_queue", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    refresh();
  });
  refresh();
  setInterval(refresh, 3000);
}

export function runsOnSSE(ev) {
  if (!$("#view-runs").classList.contains("active")) return;
  const t = ev.type, d = ev.data || {};
  if (t === "progress") {
    $("#progress-panel").hidden = false;
    const pct = d.max ? Math.round((d.value / d.max) * 100) : 0;
    $("#prog-node").textContent = `节点 ${d.node ?? ""} · 采样进度`;
    $("#prog-pct").textContent = `${d.value}/${d.max}（${pct}%）`;
    $("#prog-fill").style.width = pct + "%";
  }
  if (t === "executing" && d.node != null) {
    $("#progress-panel").hidden = false;
    $("#prog-node").textContent = `执行节点 ${d.node}…`;
  }
  if (t === "execution_start" || t === "status") refresh();
  if (t === "execution_success" || t === "execution_error" || t === "execution_interrupted") setTimeout(refresh, 800);
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
const fmtEta = (m) => m < 1 ? "<1 分钟" : `~${Math.ceil(m)} 分钟`;

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
        return `<div class="q-item"><span>任务 #${num}</span><span class="muted">${nodes} 节点</span></div>`;
      }).join("")
    : `<div class="muted">（空）</div>`;
  $("#q-pending").innerHTML = fmtQ(pend);
  $("#q-running").innerHTML = fmtQ(run);
  renderHistory();
}

async function renderHistory() {
  const r = await api("/api/history?limit=25");
  if (!r.ok) { $("#runs-list").innerHTML = `<div class="card pad muted">ComfyUI 离线，历史不可用</div>`; return; }
  const runs = await api("/api/runs");   // 带 submitted/graph 快照
  const byPid = runs.ok ? Object.fromEntries(runs.runs.map((x) => [x.prompt_id, x])) : {};
  const box = $("#runs-list");
  box.innerHTML = "";
  if (!r.history.length) { box.innerHTML = `<div class="card pad muted">还没有执行记录</div>`; return; }
  const wrap = document.createElement("div");
  wrap.className = "card";
  for (const h of r.history) {
    const row = document.createElement("div");
    row.className = "run-row";
    const info = byPid[h.prompt_id] || {};
    const name = info.name || h.name || h.prompt_id.slice(0, 8);
    const st = h.status === "success" || h.completed ? "success" : (h.status === "error" ? "error" : (h.status === "executing" ? "running" : "queued"));
    const stTxt = { success: "✓ 成功", error: "✗ 失败", running: "执行中", queued: "排队" }[st] || h.status;
    let meta = h.prompt_id.slice(0, 8);
    if (st === "running" || st === "queued") {
      const el = elapsedMin(info.submitted || "");
      meta += ` · 已 ${el < 1 ? "<1" : Math.floor(el)} 分钟 · 预计 ${fmtEta(el + estMin(name) * (st === "queued" ? 1 : 0.5))}`;
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
    const retryable = info.graph ? `<button class="btn ghost run-retry" data-pid="${h.prompt_id}">↻ 重试</button>` : "";
    row.innerHTML = `<span class="run-status ${st}">${stTxt}</span>
      <span class="run-name">${esc(name)}</span>
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
