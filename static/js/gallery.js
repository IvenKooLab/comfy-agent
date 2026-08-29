/* gallery.js — 画廊：瀑布流 + 灯箱 + 批量选择/批量归档删除 + 文件夹筛选 */
import { $, $$, api, toast, fmtSize, fmtTime, mediaUrl, goto } from "./app.js";

let items = [];
let filter = { q: "", kind: "all", sort: "new", folder: "全部" };
let lbIndex = -1;
let lastSeenMtime = 0;
let lbMeta = null;
let selected = new Set();
let folders = ["全部"];
let renderLimit = 40;      // 分页渲染：每屏 40 张，滚动到底自动加载
const PAGE = 40;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; } catch { }
  try {
    const ta = document.createElement("textarea");
    ta.value = t; ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch { return false; }
}
export { copyText };

/* —— 筛选持久化 —— */
function saveFilter() { localStorage.setItem("comfyagent_filter", JSON.stringify(filter)); }
function loadFilter() {
  try {
    const f = JSON.parse(localStorage.getItem("comfyagent_filter") || "{}");
    if (f.kind) filter.kind = f.kind;
    if (f.sort) filter.sort = f.sort;
    if (f.folder) filter.folder = f.folder;
  } catch { }
}

export function initGallery() {
  loadFilter();
  $("#g-search").addEventListener("input", (e) => { filter.q = e.target.value.trim().toLowerCase(); renderLimit = PAGE; render(); });
  $$("#g-kind .chip").forEach((c) => {
    c.classList.toggle("active", c.dataset.k === filter.kind);
    c.addEventListener("click", () => {
      $$("#g-kind .chip").forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
      filter.kind = c.dataset.k;
      saveFilter(); renderLimit = PAGE; render();
    });
  });
  $("#g-folder").addEventListener("change", (e) => { filter.folder = e.target.value; saveFilter(); renderLimit = PAGE; render(); });
  $("#g-sort").addEventListener("change", (e) => { filter.sort = e.target.value; saveFilter(); render(); });
  $("#g-refresh").addEventListener("click", () => galleryRefresh(true));
  // 批量操作
  $("#b-archive").addEventListener("click", () => batchArchive());
  $("#b-trash").addEventListener("click", () => batchTrash());
  $("#b-cancel").addEventListener("click", () => { selected.clear(); syncBatchBar(); render(); });
  // 灯箱
  $("#lb-close").addEventListener("click", closeLightbox);
  $(".lb-backdrop").addEventListener("click", closeLightbox);
  $("#lb-prev").addEventListener("click", () => step(-1));
  $("#lb-next").addEventListener("click", () => step(1));
  document.addEventListener("keydown", (e) => {
    if ($("#lightbox").hidden) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") step(-1);
    if (e.key === "ArrowRight") step(1);
  });
  // 画廊批量：Ctrl+A 全选可见 / Esc 清除（迭代26）
  document.addEventListener("keydown", (e) => {
    if (!$("#view-gallery").classList.contains("active")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
      e.preventDefault();
      visible().forEach((i) => selected.add(i.path));
      render();
      toast(`已全选 ${selected.size} 个`, "ok");
    }
    if (e.key === "Escape" && selected.size) {
      selected.clear(); syncBatchBar(); render();
    }
  });
  $("#lb-archive").addEventListener("click", doArchive);
  // 参数行：悬停复制 + 长文本展开（委托，一次绑定）
  $("#lb-summary").addEventListener("click", async (e) => {
    const cp = e.target.closest(".kv-copy");
    if (cp) {
      (await copyText(cp.dataset.copy)) ? toast("已复制到剪贴板", "ok") : toast("复制失败", "err");
      cp.textContent = "✓ 已复制";
      setTimeout(() => { cp.textContent = "复制"; }, 1500);
      return;
    }
    const ex = e.target.closest(".kv-expand");
    if (ex) {
      const kvEl = ex.closest(".kv");
      const clamped = kvEl.classList.toggle("clamp");
      ex.textContent = clamped ? "展开" : "收起";
    }
  });
  $("#lb-reveal").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (it) await api("/api/media/reveal", { method: "POST", body: { path: it.path } });
  });
  $("#lb-download").addEventListener("click", () => {
    const it = visible()[lbIndex];
    if (it) window.open(mediaUrl(it.path, { download: "1" }), "_blank");
  });
  $("#lb-trash").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (!it || !confirm(`把「${it.name}」移入回收站？`)) return;
    const r = await api("/api/media/trash", { method: "POST", body: { paths: [it.path] } });
    if (r.ok) { toast("已移入回收站（data/trash）", "ok"); selected.delete(it.path); syncBatchBar(); closeLightbox(); galleryRefresh(true); }
    else toast(r.error, "err");
  });
  $("#lb-import").addEventListener("click", () => {
    const it = visible()[lbIndex];
    if (!it) return;
    if (!lbMeta || !lbMeta.prompt) { toast("该文件没有嵌入工作流（视频/旧图可能没有）", "err"); return; }
    localStorage.setItem("pendingImport", JSON.stringify({ api: lbMeta.prompt, name: it.name.replace(/\.[^.]+$/, "") }));
    closeLightbox();
    goto("editor");
  });
  $("#lb-rerun").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (!it) return;
    if (!lbMeta || !lbMeta.prompt) { toast("没有嵌入工作流，无法直接重跑", "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: "重跑·" + it.name, prompt: lbMeta.prompt } });
    r.ok ? toast(r.msg, "ok") : toast(r.msg || r.error, "err");
    if (r.ok) goto("runs");
  });
}

export async function galleryRefresh(force) {
  const r = await api("/api/gallery" + (force ? "?force=1" : ""));
  if (!r.ok) return;
  const prevMax = lastSeenMtime;
  items = r.items;
  lastSeenMtime = items.length ? items[0].mtime : 0;
  // 文件夹清单（顶层目录）
  const dirs = new Set();
  for (const it of items) {
    const top = it.path.includes("/") ? it.path.split("/")[0] : "output 根目录";
    dirs.add(top);
  }
  folders = ["全部", ...[...dirs].sort()];
  syncFolderOptions();
  render();
  if (force && prevMax && lastSeenMtime > prevMax) toast("画廊有新成果 ✨", "ok");
}

function syncFolderOptions() {
  const sel = $("#g-folder");
  const cur = filter.folder;
  sel.innerHTML = folders.map((f) => `<option ${f === cur ? "selected" : ""}>${f}</option>`).join("");
  $("#g-sort").value = filter.sort;
}

function visible() {
  let list = items.filter((i) => {
    const top = i.path.includes("/") ? i.path.split("/")[0] : "output 根目录";
    return (filter.kind === "all" || i.kind === filter.kind)
      && (filter.folder === "全部" || top === filter.folder)
      && (!filter.q || i.name.toLowerCase().includes(filter.q));
  });
  if (filter.sort === "old") list = [...list].reverse();
  else if (filter.sort === "big") list = [...list].sort((a, b) => b.size - a.size);
  return list;
}

function render() {
  const grid = $("#gallery-grid");
  const list = visible();
  $("#g-count").textContent = `${list.length} / ${items.length} 个`;
  $("#gallery-empty").hidden = list.length > 0;
  grid.innerHTML = "";
  const shown = list.slice(0, renderLimit);
  for (const it of shown) {
    const card = document.createElement("div");
    card.className = "g-item" + (selected.has(it.path) ? " selected" : "");
    card.dataset.path = it.path;
    const src = it.kind === "video" ? mediaUrl(it.path, { thumb: "1" }) : mediaUrl(it.path);
    card.innerHTML = `
      <div class="g-check" title="选择">✓</div>
      <img loading="lazy" src="${src}" alt="">
      ${it.kind === "video" ? '<div class="g-play"><span>▶</span></div>' : ""}
      <div class="g-overlay">
        <div class="g-acts">
          <button class="g-act" data-act="rerun" title="重新生成">↻</button>
          <button class="g-act" data-act="edit" title="导入编辑器">⑃</button>
          <button class="g-act" data-act="archive" title="归档到知识库">◈</button>
          <button class="g-act" data-act="download" title="下载">↓</button>
          <button class="g-act del" data-act="del" title="删除">✕</button>
        </div>
      </div>
      <span class="g-badge">${it.kind === "video" ? "视频" : "图片"}${it.w ? " · " + it.w + "×" + it.h : ""}</span>
      <div class="g-foot"><span class="g-name" title="${it.path}">${it.name}</span><span class="g-date">${fmtTime(it.mtime)}</span></div>`;
    card.addEventListener("click", (e) => {
      if (e.target.closest(".g-act") || e.target.closest(".g-check")) return;
      if (e.ctrlKey || e.metaKey) { toggleSelect(it.path); return; }
      openLightbox(list, list.indexOf(it));
    });
    card.querySelector(".g-check").addEventListener("click", (e) => { e.stopPropagation(); toggleSelect(it.path); });
    wireActions(card, it);
    // 视频 hover 600ms 后静默预览播放（迭代15）
    if (it.kind === "video") {
      let hv = null;
      const t = setTimeout(() => {
        hv = document.createElement("video");
        hv.src = mediaUrl(it.path); hv.muted = true; hv.loop = true; hv.playsInline = true;
        hv.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;background:#000;position:absolute;inset:0";
        card.appendChild(hv);
        hv.play().catch(() => { });
      }, 600);
      card.addEventListener("mouseleave", () => { clearTimeout(t); hv?.remove(); hv = null; });
    }
    grid.appendChild(card);
  }
  // 分页哨兵
  const oldSentinel = $("#gallery-more");
  if (oldSentinel) oldSentinel.remove();
  if (list.length > shown.length) {
    const s = document.createElement("div");
    s.id = "gallery-more";
    s.className = "muted";
    s.style.cssText = "text-align:center;padding:16px;column-span:all;cursor:pointer";
    s.textContent = `↓ 加载更多（还有 ${list.length - shown.length} 个）`;
    s.addEventListener("click", () => { renderLimit += PAGE; render(); });
    grid.appendChild(s);
  }
  syncBatchBar();
}

function wireActions(card, it) {
  card.querySelector('[data-act="download"]')?.addEventListener("click", (e) => {
    e.stopPropagation(); window.open(mediaUrl(it.path, { download: "1" }), "_blank");
  });
  card.querySelector('[data-act="archive"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const r = await api("/api/obsidian/archive", {
      method: "POST", body: { paths: [it.path], title: it.name.replace(/\.[^.]+$/, "").slice(0, 40) },
    });
    if (r.ok) { toast(`已归档：${r.note}`, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
    else toast(r.error || "归档失败", "err");
  });
  card.querySelector('[data-act="edit"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast("该文件没有嵌入工作流", "err"); return; }
    localStorage.setItem("pendingImport", JSON.stringify({ api: meta.prompt, name: it.name.replace(/\.[^.]+$/, "") }));
    goto("editor");
  });
  card.querySelector('[data-act="rerun"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast("该文件没有嵌入工作流，无法直接重跑", "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: "重跑·" + it.name, prompt: meta.prompt } });
    r.ok ? toast(r.msg, "ok") : toast(r.msg || r.error, "err");
  });
  card.querySelector('[data-act="del"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm(`把「${it.name}」移入回收站？`)) return;
    const r = await api("/api/media/trash", { method: "POST", body: { paths: [it.path] } });
    if (r.ok) { toast("已移入回收站", "ok"); galleryRefresh(true); }
    else toast(r.error, "err");
  });
}

/* —— 批量 —— */
function toggleSelect(path) {
  selected.has(path) ? selected.delete(path) : selected.add(path);
  const card = $(`#gallery-grid .g-item[data-path="${CSS.escape(path)}"]`);
  card?.classList.toggle("selected", selected.has(path));
  syncBatchBar();
}
function syncBatchBar() {
  const bar = $("#batch-bar");
  bar.hidden = selected.size === 0;
  $("#batch-n").textContent = selected.size;
}
async function batchArchive() {
  const paths = [...selected];
  if (!paths.length) return;
  const r = await api("/api/obsidian/archive", { method: "POST", body: { paths, title: `批量归档${paths.length}个` } });
  if (r.ok) { toast(`已归档 ${r.count} 个到 ${r.note}`, "ok"); selected.clear(); syncBatchBar(); render(); }
  else toast(r.error || "归档失败", "err");
}
async function batchTrash() {
  const paths = [...selected];
  if (!paths.length || !confirm(`把选中的 ${paths.length} 个文件移入回收站？`)) return;
  const r = await api("/api/media/trash", { method: "POST", body: { paths } });
  if (r.ok) { toast(`已移入回收站 ${r.count} 个`, "ok"); selected.clear(); syncBatchBar(); galleryRefresh(true); }
  else toast(r.error, "err");
}

/* —— 灯箱 —— */
function openLightbox(list, idx) { lbIndex = idx; $("#lightbox").hidden = false; renderLightbox(list); }
function closeLightbox() { $("#lightbox").hidden = true; $("#lb-media").innerHTML = ""; }
function step(delta) {
  const list = visible();
  if (!list.length) return;
  lbIndex = (lbIndex + delta + list.length) % list.length;
  renderLightbox(list);
}
export function openLightboxPublic(list, idx) { openLightbox(list, idx); }

async function renderLightbox(list) {
  const it = list[lbIndex];
  if (!it) return;
  $("#lb-title").textContent = it.name;
  $("#lb-info").innerHTML = `
    <div>📁 ${it.path}</div>
    <div>💾 ${fmtSize(it.size)} · ${new Date(it.mtime * 1000).toLocaleString("zh-CN")}${it.w ? ` · ${it.w}×${it.h}` : ""}</div>
    <div>${lbIndex + 1} / ${list.length}</div>`;
  const box = $("#lb-media");
  box.innerHTML = "";
  lbMeta = null;
  $("#lb-summary").innerHTML = `<div class="muted">读取生成参数…</div>`;
  if (it.kind === "video") {
    const v = document.createElement("video");
    v.src = mediaUrl(it.path); v.controls = true; v.autoplay = true; v.loop = true;
    box.appendChild(v);
  } else {
    const img = document.createElement("img");
    img.src = mediaUrl(it.path);
    box.appendChild(img);
  }
  const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
  if (meta.ok) {
    lbMeta = meta;
    const s = meta.summary;
    if (s && (s.model || s.prompt || s.seed != null)) {
      $("#lb-summary").innerHTML =
        kv("模型", s.model) + kv("采样", `${s.sampler ?? "-"} · ${s.steps ?? "-"}步 · cfg ${s.cfg ?? "-"}`) +
        kv("种子", s.seed) + kv("尺寸", s.dimensions) + kv("提示词", s.prompt, true) + kv("负向", s.negative, true);
    } else {
      $("#lb-summary").innerHTML = `<div class="muted">未嵌入生成参数</div>`;
    }
  } else {
    $("#lb-summary").innerHTML = `<div class="muted">（元数据读取失败）</div>`;
  }
}

/* 参数行构造：长文本可展开，悬停浮现复制按钮 */
function kv(label, value, expandable = false) {
  if (value == null || value === "") return "";
  const v = String(value);
  return `<div class="kv${expandable && v.length > 90 ? " clamp" : ""}">
    <span>${label}</span><span class="kv-val">${esc(v)}</span>
    <button class="kv-copy" data-copy="${esc(v)}" title="复制">复制</button>
    ${expandable && v.length > 90 ? '<button class="kv-expand" data-exp="1">展开</button>' : ""}
  </div>`;
}

async function doArchive() {
  const it = visible()[lbIndex];
  if (!it) return;
  const note = $("#lb-note-text").value.trim();
  const r = await api("/api/obsidian/archive", {
    method: "POST", body: { paths: [it.path], title: it.name.replace(/\.[^.]+$/, "").slice(0, 40), note },
  });
  if (r.ok) { toast(`已归档到 Obsidian：${r.note}`, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
  else toast(r.error || "归档失败", "err");
}
