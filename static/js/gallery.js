/* gallery.js — 成果画廊：瀑布流 + 灯箱 + 元数据 + 实时刷新 */
import { $, $$, api, toast, fmtSize, fmtTime, mediaUrl, goto } from "./app.js";

let items = [];
let filter = { q: "", kind: "all", sort: "new" };
let lbIndex = -1;
let lastSeenMtime = 0;
let lbMeta = null;

export function initGallery() {
  $("#g-search").addEventListener("input", (e) => { filter.q = e.target.value.trim().toLowerCase(); render(); });
  $$("#g-kind .chip").forEach((c) => c.addEventListener("click", () => {
    $$("#g-kind .chip").forEach((x) => x.classList.remove("active"));
    c.classList.add("active");
    filter.kind = c.dataset.k;
    render();
  }));
  $("#g-sort").addEventListener("change", (e) => { filter.sort = e.target.value; render(); });
  $("#g-refresh").addEventListener("click", () => galleryRefresh(true));
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
  $("#lb-archive").addEventListener("click", doArchive);
  $("#lb-reveal").addEventListener("click", async () => {
    const it = items[lbIndex];
    if (it) await api("/api/media/reveal", { method: "POST", body: { path: it.path } });
  });
  $("#lb-download").addEventListener("click", () => {
    const it = items[lbIndex];
    if (it) window.open(mediaUrl(it.path, { download: "1" }), "_blank");
  });
  $("#lb-trash").addEventListener("click", async () => {
    const it = items[lbIndex];
    if (!it || !confirm(`把「${it.name}」移入回收站？`)) return;
    const r = await api("/api/media/trash", { method: "POST", body: { paths: [it.path] } });
    if (r.ok) { toast("已移入回收站（data/trash）", "ok"); closeLightbox(); galleryRefresh(true); }
    else toast(r.error, "err");
  });
  $("#lb-import").addEventListener("click", () => {
    const it = items[lbIndex];
    if (!it) return;
    if (!lbMeta || !lbMeta.prompt) { toast("该文件没有嵌入工作流（视频/旧图可能没有）", "err"); return; }
    localStorage.setItem("pendingImport", JSON.stringify({
      api: lbMeta.prompt, name: it.name.replace(/\.[^.]+$/, ""),
    }));
    closeLightbox();
    goto("editor");
  });
  $("#lb-rerun").addEventListener("click", async () => {
    const it = items[lbIndex];
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
  render();
  // 标出新文件
  if (force && prevMax && lastSeenMtime > prevMax) {
    $$("#gallery-grid .g-item").forEach((el) => {
      const it = items.find((i) => i.path === el.dataset.path);
      if (it && it.mtime > prevMax) el.classList.add("fresh");
    });
    toast("画廊有新成果 ✨", "ok");
  }
}

function visible() {
  let list = items.filter((i) =>
    (filter.kind === "all" || i.kind === filter.kind) &&
    (!filter.q || i.name.toLowerCase().includes(filter.q)));
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
  for (const it of list) {
    const card = document.createElement("div");
    card.className = "g-item";
    card.dataset.path = it.path;
    const src = it.kind === "video" ? mediaUrl(it.path, { thumb: "1" }) : mediaUrl(it.path, it.thumb ? { thumb: "1" } : {});
    const inner = it.kind === "video"
      ? `<img loading="lazy" src="${src}" alt=""><div class="g-play">▶</div>`
      : `<img loading="lazy" src="${src}" alt="">`;
    card.innerHTML = `${inner}<span class="g-badge">${it.kind === "video" ? "MP4" : "IMG"}${it.w ? " · " + it.w + "×" + it.h : ""}</span>
      <div class="g-foot"><span class="g-name" title="${it.path}">${it.name}</span><span class="g-date">${fmtTime(it.mtime)}</span></div>`;
    card.addEventListener("click", () => openLightbox(list, list.indexOf(it)));
    // 视频卡片 hover 预览
    card.addEventListener("mouseenter", () => hoverPreview(card, it));
    card.addEventListener("mouseleave", () => hoverStop(card));
    grid.appendChild(card);
  }
}

let hoverTimer = null;
function hoverPreview(card, it) {
  if (it.kind !== "video") return;
  hoverTimer = setTimeout(() => {
    hoverStop(card);
    const v = document.createElement("video");
    v.src = mediaUrl(it.path); v.muted = true; v.loop = true; v.playsInline = true;
    v.style.cssText = "width:100%;display:block;background:#000";
    v.className = "hover-video";
    card.querySelector("img")?.replaceWith(v);
    v.play().catch(() => {});
  }, 500);
}
function hoverStop(card) {
  clearTimeout(hoverTimer);
  card.querySelectorAll(".hover-video")?.forEach((v) => v.removeEventListener);
}

function openLightbox(list, idx) {
  lbIndex = idx;
  $("#lightbox").hidden = false;
  renderLightbox(list);
}
function closeLightbox() { $("#lightbox").hidden = true; $("#lb-media").innerHTML = ""; }
function step(delta) {
  const list = visible();
  if (!list.length) return;
  lbIndex = (lbIndex + delta + list.length) % list.length;
  renderLightbox(list);
}

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
    v.src = mediaUrl(it.path); v.controls = true; v.autoplay = true; v.loop = true; v.muted = false;
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
      const kv = (k, v) => v == null || v === "" ? "" : `<div class="kv"><span>${k}</span><span>${v}</span></div>`;
      $("#lb-summary").innerHTML =
        kv("模型", s.model) + kv("采样", `${s.sampler ?? "-"} · ${s.steps ?? "-"}步 · cfg ${s.cfg ?? "-"}`) +
        kv("种子", s.seed) + kv("尺寸", s.dimensions) +
        kv("提示词", s.prompt) + kv("负向", s.negative);
    } else {
      $("#lb-summary").innerHTML = `<div class="muted">未嵌入生成参数</div>`;
    }
  } else {
    $("#lb-summary").innerHTML = `<div class="muted">（元数据读取失败）</div>`;
  }
}

async function doArchive() {
  const it = visible()[lbIndex];
  if (!it) return;
  const note = $("#lb-note-text").value.trim();
  const r = await api("/api/obsidian/archive", {
    method: "POST",
    body: { paths: [it.path], title: it.name.replace(/\.[^.]+$/, "").slice(0, 40), note },
  });
  if (r.ok) {
    toast(`已归档到 Obsidian：${r.note}`, "ok");
    const a = document.createElement("a"); a.href = r.uri; a.click();
  } else toast(r.error || "归档失败", "err");
}
