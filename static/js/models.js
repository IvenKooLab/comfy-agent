/* models.js — 模型管理：本地扫描 / 预设套件一键下载 / 下载进度 */
import { $, api, toast, goto } from "./app.js";
import { t, tf } from "./i18n.js";
import { uiConfirm } from "./ui.js";

let suites = [], dirs = {}, root = "", tab = "", timer = null, query = "";

const fmtSize = (n) => (n == null ? "" : n >= 2 ** 30 ? (n / 2 ** 30).toFixed(2) + " GB"
  : n >= 2 ** 20 ? (n / 2 ** 20).toFixed(1) + " MB" : Math.round(n / 1024) + " KB");
const fmtDate = (ts) => { const d = new Date((ts || 0) * 1000); return isNaN(d) ? "" :
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function loadPresets() {
  const r = await api("/api/models/presets");
  if (r.ok) { suites = r.suites; renderSuites(); }
}

async function loadLocal() {
  const r = await api("/api/models/scan");
  if (!r.ok) return;
  root = r.root; dirs = r.dirs;
  if (!tab || !dirs[tab]) tab = Object.keys(dirs).find((k) => (dirs[k] || []).length) || Object.keys(dirs)[0];
  renderTabs(); renderLocal();
}

function renderSuites() {
  const dls = {};   // "dir/name" -> job（渲染时套用进行中的下载态）
  api("/api/models/downloads").then((r) => {
    (r.downloads || []).forEach((j) => { dls[j.key] = j; renderSuitesOnce(dls); });
  });
  renderSuitesOnce(dls);
}

function renderSuitesOnce(dls) {
  const box = $("#md-suites");
  box.innerHTML = suites.map((s) => {
    const okN = s.installed_count;
    const rows = s.models.map((m) => {
      const key = `${m.dir}/${m.name}`;
      const j = dls[key];
      let status, action = "";
      if (m.installed) {
        status = `<span class="badge" style="color:var(--brand-2)">✓ ${t("md.installed")}</span>`;
      } else if (j && j.status === "downloading") {
        const pct = j.total ? Math.min(100, Math.round((j.done / j.total) * 100)) : 0;
        status = `<div class="row" style="gap:8px;flex-wrap:nowrap"><div class="mdbar"><div style="width:${pct}%"></div></div><span class="muted">${pct}%</span></div>`;
      } else if (j && j.status === "error") {
        status = `<span class="badge" style="color:#f66">✗ ${esc((j.error || "").slice(0, 40))}</span>`;
        action = m.url ? `<button class="btn sm" data-dl="${s.id}" data-name="${esc(m.name)}">${t("md.retry")}</button>` : "";
      } else if (j && j.status === "done") {
        status = `<span class="badge" style="color:var(--brand-2)">✓ ${t("md.dl.done")}</span>`;
        action = "";
      } else {
        status = `<span class="muted">${fmtSize(m.size)}</span>`;
        action = m.url ? `<button class="btn sm primary" data-dl="${s.id}" data-name="${esc(m.name)}">${t("md.download")}</button>` : `<span class="muted">${t("md.nourl")}</span>`;
      }
      return `<tr><td class="mono">${esc(m.name)}</td><td class="muted">${esc(m.dir)}</td><td>${status}</td><td style="text-align:right">${action}</td></tr>`;
    }).join("");
    return `<div class="card pad" style="margin-bottom:12px">
      <div class="row" style="justify-content:space-between;margin-bottom:8px">
        <div><b>${esc(s.name)}</b> <span class="badge">${okN}/${s.model_count} ${t("md.ready")}</span>
          <div class="muted" style="margin-top:4px">${esc(s.desc)}</div></div>
      </div>
      <table class="tbl" style="width:100%"><tbody>${rows}</tbody></table>
    </div>`;
  }).join("");
  box.querySelectorAll("[data-dl]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    const r = await api("/api/models/download", { method: "POST", body: { suite: b.dataset.dl, name: b.dataset.name } });
    if (!r.ok) { toast(r.error, "err"); b.disabled = false; return; }
    renderSuites();
  }));
}

function renderTabs() {
  const tabs = $("#md-tabs");
  tabs.innerHTML = Object.keys(dirs).map((d) => {
    const n = (dirs[d] || []).length;
    return `<button class="chip ${d === tab ? "active" : ""}" data-tab="${esc(d)}">${esc(d)}${n ? ` (${n})` : ""}</button>`;
  }).join("");
  tabs.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; renderTabs(); renderLocal(); }));
}

function renderLocal() {
  const tb = $("#md-local");
  const q = query.toLowerCase();
  const items = (dirs[tab] || []).filter((i) => !q || i.name.toLowerCase().includes(q));
  tb.innerHTML = items.length ? items.map((i) =>
    `<tr><td class="mono">${esc(i.name)}</td><td class="muted">${esc(tab)}</td><td>${fmtSize(i.size)}</td><td class="muted">${fmtDate(i.mtime)}</td></tr>`
  ).join("") : `<tr><td colspan="4" class="muted" style="text-align:center;padding:24px">${t("md.none")}</td></tr>`;
}

function startPolling() {
  clearInterval(timer);
  timer = setInterval(async () => {
    if (document.querySelector("#view-models:not(.active)")) return;
    const r = await api("/api/models/downloads");
    const active = (r.downloads || []).some((j) => j.status === "downloading");
    if (active) renderSuitesOnce(Object.fromEntries((r.downloads || []).map((j) => [j.key, j])));
  }, 2000);
}

export function initModels() {
  loadPresets(); loadLocal(); startPolling();
  $("#md-refresh").addEventListener("click", () => { loadPresets(); loadLocal(); });
  $("#md-open").addEventListener("click", async () => {
    const r = await api("/api/models/open_folder", { method: "POST", body: {} });
    if (!r.ok) toast(r.error, "err");
  });
  $("#md-search").addEventListener("input", (e) => { query = e.target.value.trim(); renderLocal(); });
}

/* 模板载入时的缺失模型提示（由 templates.js 调用） */
export async function warnMissingModels(missing) {
  if (!missing?.length) return false;
  const names = missing.map((m) => m.file).slice(0, 5).join("\n");
  const more = missing.length > 5 ? t("md.more") : "";
  const yes = await uiConfirm(`${tf(t("md.missing.ask"), missing.length)}\n${names}${more}`, { okText: t("md.godl"), danger: false });
  if (yes) { loadLocal(); loadPresets(); goto("models"); }
  return yes;
}
