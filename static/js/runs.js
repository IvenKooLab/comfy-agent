/* runs.js — 任务页：队列 + 进度 + 历史 */
import { $, $$, api, toast, fmtTime, mediaUrl, goto } from "./app.js";

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
  if (t === "executing") {
    if (d.node != null) {
      $("#progress-panel").hidden = false;
      $("#prog-node").textContent = `执行节点 ${d.node}…`;
    }
  }
  if (t === "execution_start" || t === "status") refresh();
  if (t === "execution_success" || t === "execution_error" || t === "execution_interrupted") {
    setTimeout(refresh, 800);
  }
}

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
  const box = $("#runs-list");
  box.innerHTML = "";
  if (!r.history.length) { box.innerHTML = `<div class="card pad muted">还没有执行记录</div>`; return; }
  const wrap = document.createElement("div");
  wrap.className = "card";
  for (const h of r.history) {
    const row = document.createElement("div");
    row.className = "run-row";
    const st = h.status === "success" || h.completed ? "success" : (h.status === "error" ? "error" : (h.status === "executing" ? "running" : "queued"));
    const stTxt = { success: "✓ 成功", error: "✗ 失败", running: "执行中", queued: "排队" }[st] || h.status;
    const outs = (h.outputs || []).map((o) => {
      const isVid = /\.(mp4|webm|gif|mov|mkv)$/i.test(o.filename);
      const rel = (o.subfolder ? o.subfolder + "/" : "") + o.filename;
      const qs = `filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder)}&type=${o.type}`;
      const src = o.type === "output" ? mediaUrl(rel) : "/api/comfyview?" + qs;
      const tSrc = (o.type === "output" && isVid) ? mediaUrl(rel, { thumb: "1" }) : src;
      return `<img src="${tSrc}" loading="lazy" title="${esc(o.filename)}${isVid ? "（点击播放）" : ""}" data-full="${src}">`;
    }).join("");
    row.innerHTML = `<span class="run-status ${st}">${stTxt}</span>
      <span class="run-name">${esc(h.name || h.prompt_id.slice(0, 8))}</span>
      <span class="muted">${esc(h.prompt_id.slice(0, 8))}</span>
      <div class="run-outs">${outs}</div>`;
    row.querySelectorAll("img").forEach((im) => im.addEventListener("click", () => window.open(im.dataset.full, "_blank")));
    row.querySelectorAll("video").forEach((v) => v.addEventListener("click", () => window.open(v.src, "_blank")));
    wrap.appendChild(row);
  }
  box.appendChild(wrap);
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
