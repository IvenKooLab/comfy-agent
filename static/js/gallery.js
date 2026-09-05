/* gallery.js — 画廊：瀑布流 + 灯箱 + 批量选择/批量归档删除 + 文件夹筛选 */
import { $, $$, api, toast, fmtSize, fmtTime, mediaUrl, goto } from "./app.js";
import { t, tf } from "./i18n.js";
import { uiConfirm } from "./ui.js";

let items = [];
let filter = { q: "", kind: "all", sort: "new", folder: "" };
let lbIndex = -1;
let lastSeenMtime = 0;
let lbMeta = null;
let selected = new Set();
let folders = [];
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
    if (filter.folder === "全部" || filter.folder === "All") filter.folder = "";
  } catch { }
}

export function initGallery() {
  loadFilter();
  let searchT = null;
  $("#g-search").addEventListener("input", (e) => {
    clearTimeout(searchT);
    searchT = setTimeout(() => { filter.q = e.target.value.trim().toLowerCase(); renderLimit = PAGE; render(); }, 150);
  });
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
  window.addEventListener("langchange", () => { syncFolderOptions(); render(); });
  $("#g-sort").addEventListener("change", (e) => { filter.sort = e.target.value; saveFilter(); render(); });
  $("#g-refresh").addEventListener("click", () => galleryRefresh(true));
  $("#g-empty-go")?.addEventListener("click", () => goto("create"));
  // 批量操作
  $("#b-archive").addEventListener("click", () => batchArchive());
  $("#b-trash").addEventListener("click", () => batchTrash());
  $("#b-cancel").addEventListener("click", () => { selected.clear(); syncBatchBar(); render(); });
  $("#b-concat").addEventListener("click", batchConcat);
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
      toast(tf("misc.select.all.n", selected.size), "ok");
    }
    if (e.key === "Escape" && selected.size) {
      selected.clear(); syncBatchBar(); render();
    }
  });
  $("#lb-archive").addEventListener("click", doArchive);
  // 图生文反推：视觉 LLM 从图生成英文提示词
  $("#lb-i2p").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (!it || it.kind !== "image") { toast(t("err.image.only"), "err"); return; }
    const btn = $("#lb-i2p");
    btn.disabled = true; btn.textContent = t("st.i2p");
    try {
      const r = await api("/api/image_to_prompt", { method: "POST", body: { path: it.path } });
      if (r.ok && r.prompt) {
        const box = $("#lb-summary");
        box.innerHTML = `<div class="kv"><span>${t("lb.i2p")}</span><span class="kv-val">${r.prompt.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span></div>
          <button class="kv-copy" id="lb-i2p-copy">${t("lb.copy")}</button>`;
        box.querySelector("#lb-i2p-copy").addEventListener("click", () => {
          navigator.clipboard.writeText(r.prompt).then(() => { btn.textContent = t("st.ok"); setTimeout(() => btn.textContent = t("lb.copy"), 1200); });
        });
      } else toast(r.error, "err");
    } finally {
      btn.disabled = false; btn.textContent = t("lb.i2p.btn");
    }
  });
  // 参数行：悬停复制 + 长文本展开（委托，一次绑定）
  // 复制反馈用按钮内联状态（✓ 已复制），不弹全局 toast——避免遮挡灯箱关闭按钮
  $("#lb-summary").addEventListener("click", async (e) => {
    const cp = e.target.closest(".kv-copy");
    if (cp) {
      const ok = await copyText(cp.dataset.copy);
      cp.textContent = ok ? "✓ " + t("toast.copied") : t("toast.copy.fail");
      setTimeout(() => { cp.textContent = t("lb.copy"); }, 1500);
      return;
    }
    const ex = e.target.closest(".kv-expand");
    if (ex) {
      const kvEl = ex.closest(".kv");
      const clamped = kvEl.classList.toggle("clamp");
      ex.textContent = clamped ? t("lb.expand") : t("lb.collapse");
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
    if (!it || !(await uiConfirm(tf("misc.confirm.delete", it.name)))) return;
    const r = await api("/api/media/trash", { method: "POST", body: { paths: [it.path] } });
    if (r.ok) { toast(t("toast.trashed"), "ok"); selected.delete(it.path); syncBatchBar(); closeLightbox(); galleryRefresh(true); }
    else toast(r.error, "err");
  });
  $("#lb-import").addEventListener("click", () => {
    const it = visible()[lbIndex];
    if (!it) return;
    if (!lbMeta || !lbMeta.prompt) { toast(t("err.no.embed"), "err"); return; }
    localStorage.setItem("pendingImport", JSON.stringify({ api: lbMeta.prompt, name: it.name.replace(/\.[^.]+$/, "") }));
    closeLightbox();
    goto("editor");
  });
  $("#lb-rerun").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (!it) return;
    if (!lbMeta || !lbMeta.prompt) { toast(t("err.no.embed.rerun"), "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: t("name.rerun.prefix") + it.name, prompt: lbMeta.prompt } });
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
    const top = it.path.includes("/") ? it.path.split("/")[0] : t("g.root");
    dirs.add(top);
  }
  folders = [...dirs].sort();
  syncFolderOptions();
  render();
  if (force && prevMax && lastSeenMtime > prevMax) toast(t("toast.new.work"), "ok");
}

function syncFolderOptions() {
  const sel = $("#g-folder");
  const cur = filter.folder;
  sel.innerHTML = `<option value="" ${cur === "" ? "selected" : ""}>${t("gallery.all")}</option>` + folders.map((f) => `<option ${f === cur ? "selected" : ""}>${f}</option>`).join("");
  $("#g-sort").value = filter.sort;
}

function visible() {
  let list = items.filter((i) => {
    const top = i.path.includes("/") ? i.path.split("/")[0] : t("g.root");
    return (filter.kind === "all" || i.kind === filter.kind)
      && (filter.folder === "" || top === filter.folder)
      && (!filter.q || i.name.toLowerCase().includes(filter.q));
  });
  if (filter.sort === "old") list = [...list].reverse();
  else if (filter.sort === "big") list = [...list].sort((a, b) => b.size - a.size);
  return list;
}

function render() {
  const grid = $("#gallery-grid");
  const list = visible();
  $("#g-count").textContent = tf("g.count.tpl", list.length, items.length);
  $("#gallery-empty").hidden = list.length > 0;
  // 搜索/筛选无结果 ≠ 没有成果物：区分文案与「去创作」CTA
  if (!list.length) {
    const hasData = items.length > 0;
    const p = $("#gallery-empty p");
    if (p) p.textContent = t(hasData ? "empty.gallery.search" : "gallery.empty");
    const go = $("#g-empty-go");
    if (go) go.style.display = hasData ? "none" : "";
  }
  grid.innerHTML = "";
  const shown = list.slice(0, renderLimit);
  for (const it of shown) {
    const card = document.createElement("div");
    card.className = "g-item" + (selected.has(it.path) ? " selected" : "");
    card.dataset.path = it.path;
    const src = it.kind === "video" ? mediaUrl(it.path, { thumb: "1" }) : mediaUrl(it.path);
    card.innerHTML = `
      <div class="g-check" title="${t("lb.select")}">✓</div>
      <img loading="lazy" src="${src}" alt="">
      ${it.kind === "video" ? '<div class="g-play"><span>▶</span></div>' : ""}
      <div class="g-overlay">
        <div class="g-acts">
          <button class="g-act" data-act="rerun" title="${t("act.rerun")}">↻</button>
          <button class="g-act" data-act="edit" title="${t("act.edit")}">⑃</button>
          <button class="g-act" data-act="archive" title="${t("lb.archive")}">◈</button>
          <button class="g-act" data-act="download" title="${t("lb.download")}">↓</button>
          <button class="g-act del" data-act="del" title="${t("act.delete")}">✕</button>
        </div>
      </div>
      <span class="g-badge">${it.kind === "video" ? t("gallery.video") : t("gallery.image")}${it.w ? " · " + it.w + "×" + it.h : ""}</span>
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
    s.textContent = tf("misc.load.more.n", list.length - shown.length);
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
    if (r.ok) { toast(t("toast.archived") + r.note, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
    else toast(r.error || t("toast.archive.fail"), "err");
  });
  card.querySelector('[data-act="edit"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast(t("err.no.embed"), "err"); return; }
    localStorage.setItem("pendingImport", JSON.stringify({ api: meta.prompt, name: it.name.replace(/\.[^.]+$/, "") }));
    goto("editor");
  });
  card.querySelector('[data-act="rerun"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast(t("err.no.embed.rerun"), "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: t("name.rerun.prefix") + it.name, prompt: meta.prompt } });
    r.ok ? toast(r.msg, "ok") : toast(r.msg || r.error, "err");
  });
  card.querySelector('[data-act="del"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!(await uiConfirm(tf("misc.confirm.delete", it.name)))) return;
    const r = await api("/api/media/trash", { method: "POST", body: { paths: [it.path] } });
    if (r.ok) { toast(t("toast.trashed"), "ok"); galleryRefresh(true); }
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
  const vids = [...selected].filter((p) => /\.(mp4|webm|mov|mkv)$/i.test(p)).length;
  $("#b-concat").hidden = vids < 2;
  $("#b-concat").textContent = tf("g.concat.n", vids);
}

async function batchConcat() {
  const vids = [...selected].filter((p) => /\.(mp4|webm|mov|mkv)$/i.test(p));
  if (vids.length < 2) return;
  if (!(await uiConfirm(tf("misc.confirm.concat", vids.length)))) return;
  const r = await api("/api/concat", { method: "POST", body: { paths: vids, name: t("name.concat") } });
  if (r.ok) { toast(r.msg + t("st.in.gallery"), "ok"); selected.clear(); syncBatchBar(); galleryRefresh(true); }
  else toast(r.error, "err");
}
async function batchArchive() {
  const paths = [...selected];
  if (!paths.length) return;
  const r = await api("/api/obsidian/archive", { method: "POST", body: { paths, title: tf("g.batcharch", paths.length) } });
  if (r.ok) { toast(tf("toast.archived.n", r.count, r.note), "ok"); selected.clear(); syncBatchBar(); render(); }
  else toast(r.error || t("toast.archive.fail"), "err");
}
async function batchTrash() {
  const paths = [...selected];
  if (!paths.length || !(await uiConfirm(tf("misc.confirm.del.multi", paths.length)))) return;
  const r = await api("/api/media/trash", { method: "POST", body: { paths } });
  if (r.ok) { toast(tf("toast.trashed.n", r.count), "ok"); selected.clear(); syncBatchBar(); galleryRefresh(true); }
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
  $("#lb-summary").innerHTML = `<div class="muted">${t("st.meta")}</div>`;
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
        kv(t("kv.model"), s.model) + kv(t("kv.sampler"), `${s.sampler ?? "-"} · ${s.steps ?? "-"}${t("unit.steps")} · cfg ${s.cfg ?? "-"}`) +
        kv(t("kv.seed"), s.seed) + kv(t("kv.size"), s.dimensions) + kv(t("kv.prompt"), s.prompt, true) + kv(t("kv.negative"), s.negative, true);
    } else {
      $("#lb-summary").innerHTML = `<div class="muted">${t("meta.none")}</div>`;
    }
  } else {
    $("#lb-summary").innerHTML = `<div class="muted">${t("meta.fail")}</div>`;
  }
}

/* 参数行构造：长文本可展开，悬停浮现复制按钮 */
function kv(label, value, expandable = false) {
  if (value == null || value === "") return "";
  const v = String(value);
  return `<div class="kv${expandable && v.length > 90 ? " clamp" : ""}">
    <span>${label}</span><span class="kv-val">${esc(v)}</span>
    <button class="kv-copy" data-copy="${esc(v)}" title="${t("lb.copy")}">${t("lb.copy")}</button>
    ${expandable && v.length > 90 ? `<button class="kv-expand" data-exp="1">${t("lb.expand")}</button>` : ""}
  </div>`;
}

async function doArchive() {
  const it = visible()[lbIndex];
  if (!it) return;
  const note = $("#lb-note-text").value.trim();
  const r = await api("/api/obsidian/archive", {
    method: "POST", body: { paths: [it.path], title: it.name.replace(/\.[^.]+$/, "").slice(0, 40), note },
  });
  if (r.ok) { toast(t("toast.archived") + r.note, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
  else toast(r.error || t("toast.archive.fail"), "err");
}
