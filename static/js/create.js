/* create.js — 创作首页：Composer + 最新创作流 */
import { $, $$, api, toast, mediaUrl, fmtTime, goto } from "./app.js";
import { copyText } from "./gallery.js";

const PARAMS_KEY = "comfyagent_params";
function loadParams() { try { return JSON.parse(localStorage.getItem(PARAMS_KEY) || "{}"); } catch { return {}; } }
function saveParams(patch) {
  const p = loadParams();
  localStorage.setItem(PARAMS_KEY, JSON.stringify({ ...p, ...patch }));
}

let workflows = [];
let selSize = { w: 832, h: 1216 };
let selCount = 1;
let mode = "image";   // 'image' | 'video'
let feedItems = [];
let styles = [];
let selStyle = localStorage.getItem("comfyagent_style") || "guoman_epic";

const INSPIRE = {
  image: [
    "cinematic close-up, swordsman in white robe looking back, sea of clouds at dawn, guoman 3d style",
    "misty immortal mountains panorama, ink-wash anime style, flowing clouds",
    "chibi mascot typing on a tiny laptop, macro lens, soft light",
  ],
  video: [
    "slow dolly-in on a swordsman standing above a sea of clouds, robes flowing, morning light",
    "a cute mascot waving at the camera in a cozy room, soft warm lighting",
    "drifting clouds over ink-wash immortal mountains, seamless loop",
  ],
};
const VIDEO_HINT = "H3 W4A8 快线 · 640×352 · ≈5秒 · 4步 · 原生音频 · 约8.5分钟/条（视频尺寸由工作流锁定）";
const IMAGE_HINT = "Flux 文生图 · 20步 · 约1-2分钟/张（视队列而定）";

let characters = [];
let selChar = "";

export function initCreate() {
  // 恢复上次参数（迭代17）
  const saved = loadParams();
  if (saved.size) {
    selSize = saved.size;
    $$("#c-size .seg-btn").forEach((b) => b.classList.toggle("active", +b.dataset.w === selSize.w && +b.dataset.h === selSize.h));
  }
  if (saved.count) {
    selCount = saved.count;
    $$("#c-count .seg-btn").forEach((b) => b.classList.toggle("active", +b.dataset.n === selCount));
  }
  loadCharacters();
  // 模式切换（图/视频）
  $$("#c-mode .seg-btn").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.mode === mode) return;
    mode = b.dataset.mode;
    $$("#c-mode .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
    applyMode();
  }));
  // 尺寸/数量分段
  $$("#c-size .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#c-size .seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    selSize = { w: +b.dataset.w, h: +b.dataset.h };
    saveParams({ size: selSize });
  }));
  $$("#c-count .seg-btn").forEach((b) => b.addEventListener("click", () => {
    $$("#c-count .seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    selCount = +b.dataset.n;
    saveParams({ count: selCount });
  }));
  $("#c-dice").addEventListener("click", () => { $("#c-seed").value = Math.floor(Math.random() * 2 ** 31); });
  // 风格行滚动箭头（迭代：替代原生滚动条）
  $("#style-prev").addEventListener("click", () => $("#c-styles").scrollBy({ left: -260, behavior: "smooth" }));
  $("#style-next").addEventListener("click", () => $("#c-styles").scrollBy({ left: 260, behavior: "smooth" }));
  $("#c-styles").addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); $("#c-styles").scrollLeft += e.deltaY; }
  }, { passive: false });
  $("#c-translate").addEventListener("click", () => {
    $("#c-translate").classList.toggle("active");
    if (!$("#c-translate").classList.contains("active")) $("#c-en-preview").hidden = true;
  });
  // 英文预览悬停复制（内联反馈，不弹 toast）
  $("#c-en-preview").addEventListener("click", async (e) => {
    if (!e.target.classList.contains("en-copy")) return;
    const t = e.target.dataset.copy || "";
    const ok = await copyText(t);
    e.target.textContent = ok ? "✓ 已复制" : "复制失败";
    setTimeout(() => { e.target.textContent = "复制"; }, 1500);
  });
  $("#c-go").addEventListener("click", create);
  $("#c-prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) create();
  });
  loadStyles();
  loadWorkflows();
  refreshFeed();
  document.addEventListener("sse", (e) => {
    if (e.detail?.type === "execution_success") setTimeout(refreshFeed, 1500);
  });
}

async function loadStyles() {
  const r = await api("/api/styles");
  if (!r.ok) return;
  styles = r.styles;
  if (!styles.find((s) => s.id === selStyle)) selStyle = styles[0]?.id;
  const box = $("#c-styles");
  box.innerHTML = "";
  for (const s of styles) {
    const c = document.createElement("button");
    c.className = "style-chip" + (s.id === selStyle ? " active" : "");
    c.innerHTML = `<span class="em">${s.emoji}</span>${s.name}`;
    c.title = s.desc;
    c.addEventListener("click", () => {
      selStyle = s.id;
      localStorage.setItem("comfyagent_style", s.id);
      box.querySelectorAll(".style-chip").forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
    });
    box.appendChild(c);
  }
}

function applyMode() {
  // 灵感词
  const box = $("#c-inspire");
  box.innerHTML = "";
  for (const q of INSPIRE[mode]) {
    const c = document.createElement("button");
    c.className = "chip"; c.textContent = q;
    c.addEventListener("click", () => { $("#c-prompt").value = q; $("#c-prompt").focus(); });
    box.appendChild(c);
  }
  // 工作流过滤 + 尺寸显隐 + 预估提示
  const sel = $("#c-wf");
  const fits = workflows.filter((w) => mode === "video"
    ? /H3/.test(w.name) : !/H3/.test(w.name));
  sel.innerHTML = "";
  for (const wf of fits) {
    const o = document.createElement("option");
    o.value = wf.id || wf.name;
    o.textContent = wf.name;
    sel.appendChild(o);
  }
  const remembered = loadParams()["wf_" + mode];
  sel.value = remembered && fits.find((w) => (w.id || w.name) === remembered)
    ? remembered : (mode === "video" ? "h3-t2v" : "builtin-flux");
  if (!sel.value) sel.selectedIndex = 0;
  sel.onchange = () => saveParams({ ["wf_" + mode]: sel.value });
  $("#c-size-box").style.display = mode === "video" ? "none" : "";
  $("#c-hint").innerHTML = `<span class="dot2"></span>${mode === "video" ? VIDEO_HINT : IMAGE_HINT}`;
}

async function loadWorkflows() {
  const r = await api("/api/workflows");
  if (!r.ok) return;
  workflows = r.workflows;
  applyMode();
}

async function create() {
  const promptText = $("#c-prompt").value.trim();
  if (!promptText) { toast("先描述一下你想要的画面", "err"); $("#c-prompt").focus(); return; }
  if (mode === "video" && selCount > 2 && !confirm(`视频模式一次排 ${selCount} 条约需 ${Math.ceil(8.5 * selCount)} 分钟，确定？`)) return;
  const sel = $("#c-wf");
  const wf = workflows.find((w) => (w.id || w.name) === sel.value);
  if (!wf) { toast("没有可用工作流", "err"); return; }
  // 角色锁定串：追加到描述后一起增强，保证角色一致性
  const charObj = characters.find((c) => c.id === $("#c-char").value);
  const baseText = promptText + (charObj && charObj.lock ? "，" + charObj.lock : "");
  // 中文 → 英文增强（风格感知，可开关）
  let submitText = baseText;
  let styleParams = null;
  const styleObj = styles.find((s) => s.id === selStyle);
  if ($("#c-translate").classList.contains("active")) {
    const btn = $("#c-go");
    btn.disabled = true; btn.querySelector("span").textContent = "翻译中…";
    try {
      const en = await api("/api/enhance_prompt", {
        method: "POST", body: { text: promptText, style: selStyle, mode },
      });
      if (en.ok && en.english) {
        submitText = en.english;
        const pv = $("#c-en-preview");
        pv.innerHTML = `<span class="en-tag">EN（${en.engine}${styleObj ? " · " + styleObj.name : ""}）→</span>${en.english}<button class="kv-copy en-copy" data-copy="${en.english.replace(/"/g, "&quot;")}">复制</button>`;
        pv.hidden = false;
        if (en.note) toast(en.note, "err");
      } else {
        toast(en.error || "翻译失败，按原文提交", "err");
      }
    } finally {
      btn.disabled = false; btn.querySelector("span").textContent = "✦ 生 成";
    }
  } else if (styleObj && mode === "image") {
    // 关闭翻译也要吃到风格令牌（英文原样 + 追加）
    submitText = promptText.replace(/[.。]?\s*$/, ", ") + styleObj.tokens.replace(/,\s*$/, "");
  }
  if (styleObj && mode === "image") styleParams = { steps: 28, guidance: 3.5 };
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
              overrides: { text, ...(hasLatentSize ? { width: w, height: h } : {}) },
              params: styleParams },
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

/* ---------- 角色资产库联动 ---------- */
async function loadCharacters() {
  const r = await api("/api/characters");
  if (!r.ok) return;
  characters = r.characters;
  const box = $("#c-char-box");
  if (!characters.length) { box.style.display = "none"; return; }
  box.style.display = "";
  const sel = $("#c-char");
  const keep = loadParams().char || "";
  sel.innerHTML = `<option value="">无</option>` + characters.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  if (keep && characters.find((c) => c.id === keep)) sel.value = keep;
  sel.onchange = () => saveParams({ char: sel.value });
}
