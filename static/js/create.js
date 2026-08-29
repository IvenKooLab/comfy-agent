/* create.js — 创作首页：Composer + 最新创作流 */
import { $, $$, api, toast, mediaUrl, fmtTime, goto } from "./app.js";

let workflows = [];
let selSize = { w: 832, h: 1216 };
let selCount = 1;
let feedItems = [];

export function initCreate() {
  // 尺寸/数量分段
  $$("#c-size .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#c-size .seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    selSize = { w: +b.dataset.w, h: +b.dataset.h };
  }));
  $$("#c-count .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#c-count .seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    selCount = +b.dataset.n;
  }));
  $("#c-dice").addEventListener("click", () => { $("#c-seed").value = Math.floor(Math.random() * 2 ** 31); });
  $("#c-translate").addEventListener("click", () => {
    $("#c-translate").classList.toggle("active");
    if (!$("#c-translate").classList.contains("active")) $("#c-en-preview").hidden = true;
  });
  $$(".inspire-chips .chip").forEach((c) => c.addEventListener("click", () => {
    $("#c-prompt").value = c.textContent.trim();
    $("#c-prompt").focus();
  }));
  $("#c-go").addEventListener("click", create);
  $("#c-prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) create();
  });
  loadWorkflows();
  refreshFeed();
  // 出片后刷新 feed
  document.addEventListener("sse", (e) => {
    const t = e.detail?.type;
    if (t === "execution_success") setTimeout(refreshFeed, 1500);
  });
}

async function loadWorkflows() {
  const r = await api("/api/workflows");
  if (!r.ok) return;
  workflows = r.workflows;
  const sel = $("#c-wf");
  sel.innerHTML = "";
  for (const wf of workflows) {
    const o = document.createElement("option");
    o.value = wf.id || wf.name;
    o.textContent = wf.name;
    sel.appendChild(o);
  }
  sel.value = "builtin-flux";
}

async function create() {
  const promptText = $("#c-prompt").value.trim();
  if (!promptText) { toast("先描述一下你想要的画面", "err"); $("#c-prompt").focus(); return; }
  const sel = $("#c-wf");
  const wf = workflows.find((w) => (w.id || w.name) === sel.value);
  if (!wf) { toast("没有可用工作流", "err"); return; }
  // 中文 → 英文增强（可开关）
  let submitText = promptText;
  if ($("#c-translate").classList.contains("active") && /[\u4e00-\u9fff]/.test(promptText)) {
    const btn = $("#c-go");
    btn.disabled = true; btn.querySelector("span").textContent = "翻译中…";
    try {
      const en = await api("/api/enhance_prompt", { method: "POST", body: { text: promptText } });
      if (en.ok && en.english) {
        submitText = en.english;
        const pv = $("#c-en-preview");
        pv.innerHTML = `<span class="en-tag">EN（${en.engine}）→</span>${en.english}`;
        pv.hidden = false;
        if (en.note) toast(en.note, "err");
      } else {
        toast(en.error || "翻译失败，按原文提交", "err");
      }
    } finally {
      btn.disabled = false; btn.querySelector("span").textContent = "✦ 生 成";
    }
  }
  // 提示词里若带 WxH 则覆盖尺寸
  let { w, h } = selSize;
  const ms = submitText.match(/(\d{3,4})\s*[xX×]\s*(\d{3,4})/);
  let text = submitText;
  if (ms) { w = +ms[1]; h = +ms[2]; text = (submitText.slice(0, ms.start) + submitText.slice(ms.end)).trim(); }
  const seedRaw = $("#c-seed").value.trim();
  const seed = seedRaw === "" ? null : (+seedRaw || 0);
  // 尺寸只对"Latent 建尺寸"类工作流生效；H3 等视频工作流用自带尺寸（640×352）
  const hasLatentSize = Object.values(wf.api || {}).some((n) => /Latent/i.test(n.class_type || ""));
  const go = $("#c-go");
  go.disabled = true; go.querySelector("span").textContent = "提交中…";
  try {
    const r = await api("/api/prompt", {
      method: "POST",
      body: { name: "创作·" + promptText.slice(0, 16), prompt: wf.api, times: selCount, seed,
              overrides: { text, ...(hasLatentSize ? { width: w, height: h } : {}) } },
    });
    r.ok ? toast(r.msg + (hasLatentSize ? "" : "（视频按工作流自带尺寸）"), "ok") : toast(r.msg || r.error, "err");
    if (r.ok) $("#c-seed").value = "";
  } finally {
    go.disabled = false; go.querySelector("span").textContent = "✦ 生 成";
  }
}

export async function refreshFeed() {
  const r = await api("/api/gallery");
  if (!r.ok) return;
  feedItems = r.items.slice(0, 12);
  const box = $("#create-feed");
  box.innerHTML = "";
  for (const it of feedItems) box.appendChild(gCard(it, feedItems));
  if (!feedItems.length)
    box.innerHTML = `<div class="muted" style="padding:30px 0">还没有作品，上面输入第一条提示词吧。</div>`;
}

/* 与画廊一致的卡片（含悬浮操作） */
function gCard(it, list) {
  const idx = list.indexOf(it);
  const card = document.createElement("div");
  card.className = "g-item";
  card.dataset.path = it.path;
  const src = it.kind === "video" ? mediaUrl(it.path, { thumb: "1" }) : mediaUrl(it.path);
  card.innerHTML = `
    <img loading="lazy" src="${src}" alt="">
    ${it.kind === "video" ? '<div class="g-play"><span>▶</span></div>' : ""}
    <div class="g-overlay">
      <div class="g-acts">
        <button class="g-act" data-act="rerun" title="重新生成">↻</button>
        <button class="g-act" data-act="archive" title="归档到知识库">◈</button>
        <button class="g-act" data-act="download" title="下载">↓</button>
      </div>
    </div>
    <span class="g-badge">${it.kind === "video" ? "视频" : "图片"}${it.w ? " · " + it.w + "×" + it.h : ""}</span>
    <div class="g-foot"><span class="g-name" title="${it.path}">${it.name}</span><span class="g-date">${fmtTime(it.mtime)}</span></div>`;
  card.addEventListener("click", (e) => {
    if (e.target.closest(".g-act")) return;
    import("./gallery.js").then((g) => g.openLightboxPublic(list, idx));
  });
  card.querySelector('[data-act="download"]')?.addEventListener("click", (e) => {
    e.stopPropagation();
    window.open(mediaUrl(it.path, { download: "1" }), "_blank");
  });
  card.querySelector('[data-act="archive"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const r = await api("/api/obsidian/archive", {
      method: "POST", body: { paths: [it.path], title: it.name.replace(/\.[^.]+$/, "").slice(0, 40) },
    });
    if (r.ok) { toast(`已归档：${r.note}`, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
    else toast(r.error || "归档失败", "err");
  });
  card.querySelector('[data-act="rerun"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast("该文件没有嵌入工作流", "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: "重跑·" + it.name, prompt: meta.prompt } });
    r.ok ? toast(r.msg, "ok") : toast(r.msg || r.error, "err");
  });
  return card;
}
