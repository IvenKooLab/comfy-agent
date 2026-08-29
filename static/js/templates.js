/* templates.js — 模板库：ComfyUI 官方 632 模板浏览/搜索/一键进编辑器 */
import { $, $$, api, toast, goto } from "./app.js";

let groups = [];
let curGroup = "all";
let q = "";
let shown = 24;
let importing = false;

const GROUP_ICON = {
  "Video": "🎬", "Image": "🖼", "Use Cases": "📚", "Audio": "🔊",
  "3D Model": "🧊", "LLM": "🤖", "Image Tools": "🛠", "Video Tools": "🎬", "Node Basics": "🧱",
};

export function initTemplates() {
  $("#tpl-search").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); shown = 24; renderCards(); });
  $("#tpl-more").addEventListener("click", () => { shown += 24; renderCards(); });
  new MutationObserver(() => {
    if ($("#view-templates").classList.contains("active") && !groups.length) load();
  }).observe($("#view-templates"), { attributes: true, attributeFilter: ["class"] });
}

async function load() {
  $("#tpl-body").innerHTML = `<div class="skeleton" style="height:200px"></div>`;
  const r = await api("/api/templates/index");
  const box = $("#tpl-body");
  if (!r.ok) {
    box.innerHTML = `<div class="empty"><div class="empty-ico">📡</div><p>${r.error}</p></div>`;
    return;
  }
  groups = r.groups;
  renderGroups();
  renderCards();
}

function allTemplates() {
  const out = [];
  for (const g of groups) for (const t of g.templates) out.push({ ...t, group: g.title });
  return out;
}

function renderGroups() {
  const box = $("#tpl-groups");
  if (!box) return;
  const total = allTemplates().length;
  const row = (key, icon, label, count) =>
    `<div class="tpl-group-item${curGroup === key ? " active" : ""}" data-g="${key}">
       <span>${icon} ${label}</span><span class="muted">${count}</span></div>`;
  box.innerHTML =
    row("all", "☰", "所有模板", total) +
    groups.map((g) => row(g.title, GROUP_ICON[g.title] || "📁", g.title, g.templates.length)).join("");
  box.querySelectorAll(".tpl-group-item").forEach((el) => el.addEventListener("click", () => {
    curGroup = el.dataset.g;
    shown = 24;
    box.querySelectorAll(".tpl-group-item").forEach((x) => x.classList.toggle("active", x === el));
    renderCards();
  }));
}

function matchCount(gtitle) {
  if (curGroup !== "all" && curGroup !== gtitle) return 0;
  return 1;
}

function renderCards() {
  const grid = $("#tpl-cards");
  if (!grid) return;
  const all = allTemplates();
  const list = all.filter((t) => {
    if (curGroup !== "all" && t.group !== curGroup) return false;
    if (!q) return true;
    return (t.title + " " + t.description + " " + (t.models || []).join(" ") + " " + (t.tags || []).join(" ")).toLowerCase().includes(q);
  });
  $("#tpl-count").textContent = `${list.length} 个模板`;
  const shownList = list.slice(0, shown);
  grid.innerHTML = shownList.length ? "" : `<div class="empty" style="column-span:all"><div class="empty-ico">🔍</div><p>没有匹配的模板</p></div>`;
  for (const t of shownList) {
    const card = document.createElement("div");
    card.className = "tpl-card";
    const badge = (t.models || []).slice(0, 2).map((m) => `<span class="tpl-badge vendor">${m}</span>`).join("");
    const tags = (t.tags || []).slice(0, 2).map((tg) => `<span class="tpl-badge">${tg}</span>`).join("");
    card.innerHTML = `
      <div class="tpl-thumb"><div class="tpl-ph"><span>${t.title.slice(0, 1)}</span></div>
        <div class="tpl-badges">${badge}${tags}</div></div>
      <div class="tpl-info">
        <div class="tpl-title" title="${t.title}">${t.title}</div>
        <div class="tpl-desc">${t.description.slice(0, 90)}${t.description.length > 90 ? "…" : ""}</div>
      </div>`;
    card.addEventListener("click", () => openTemplate(t));
    grid.appendChild(card);
  }
  const old = $("#tpl-more-inline");
  if (old) old.remove();
  if (list.length > shown) {
    const btn = document.createElement("button");
    btn.id = "tpl-more-inline";
    btn.className = "btn";
    btn.style.cssText = "margin:10px auto;display:block";
    btn.textContent = `↓ 加载更多（还有 ${list.length - shown} 个）`;
    btn.addEventListener("click", () => { shown += 24; renderCards(); });
    grid.appendChild(btn);
  }
}

async function openTemplate(t) {
  if (importing) return;
  importing = true;
  toast(`拉取模板「${t.title}」…`);
  try {
    const r = await api("/api/templates/workflow", { method: "POST", body: { name: t.name } });
    if (!r.ok) { toast(r.error, "err"); return; }
    if (r.format === "api") {
      localStorage.setItem("pendingImport", JSON.stringify({ api: r.api, name: t.title.slice(0, 40) }));
    } else {
      localStorage.setItem("pendingImportUI", JSON.stringify({ ui: r.ui, name: t.title.slice(0, 40) }));
      toast("该模板为 UI 格式且自动转换失败，请在编辑器手动转换", "err");
    }
    if (r.warnings?.length) toast(r.warnings[0], "err");
    goto("editor");
    document.dispatchEvent(new CustomEvent("templates-import"));
  } finally {
    importing = false;
  }
}
