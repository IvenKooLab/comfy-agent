/* create.js — 创作首页：Composer + 最新创作流 */
import { $, $$, api, toast, mediaUrl, fmtTime, goto } from "./app.js";
import { t, tf, getLang, wfLabel } from "./i18n.js";
import { uiConfirm } from "./ui.js";
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

/* 风格 SOP 英文标签（id 对应 server.py STYLE_SOPS；服务端 name/desc 为中文） */
const STYLE_I18N = {
  guoman_epic: ["Donghua Epic", "3D donghua in the epic xianxia vein, cinematic immortal-hero feel"],
  guofeng_ink: ["Ink Wash", "Negative-space ink wash, misty mountains, eastern mood"],
  cinematic_film: ["Cinematic", "Photoreal film look, shallow depth of field, pro color grade"],
  cyber_neon: ["Cyber Neon", "Rainy-night neon, high-contrast sci-fi city"],
  storybook: ["Storybook", "Warm children's-book illustration, soft hand-drawn feel"],
  ghibli_warm: ["Warm Hand-drawn", "Ghibli-like natural light, cozy and healing"],
  thick_paint: ["Impasto Oil", "Impressionist impasto brushwork, painterly texture"],
  figure_3d: ["3D Figure", "Collector-grade figure render, studio lighting"],
  chibi_sticker: ["Chibi Sticker", "Rounded chibi, clear-sticker style"],
  poster_minimal: ["Minimal Poster", "Generous whitespace, geometric composition"],
  portrait_photo: ["Portrait Photo", "85mm portrait, natural skin texture"],
  vaporwave: ["Vaporwave", "80s retro-synth aesthetics"],
};
const styleView = (s) => (getLang() === "en" && STYLE_I18N[s.id]) ? { ...s, name: STYLE_I18N[s.id][0], desc: STYLE_I18N[s.id][1] } : s;

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
const VIDEO_HINT = () => t("create.hint.video");
const IMAGE_HINT = () => t("create.hint.image");

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
    e.target.textContent = ok ? t("st.ok") : t("st.copy.fail");
    setTimeout(() => { e.target.textContent = t("lb.copy"); }, 1500);
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
  window.addEventListener("langchange", () => { loadStyles(); loadWorkflows(); loadCharacters(); });
}

async function loadStyles() {
  const r = await api("/api/styles");
  if (!r.ok) return;
  styles = r.styles;
  if (!styles.find((s) => s.id === selStyle)) selStyle = styles[0]?.id;
  const box = $("#c-styles");
  box.innerHTML = "";
  for (const raw of styles) {
    const s = styleView(raw);
    const c = document.createElement("button");
    c.className = "style-chip" + (raw.id === selStyle ? " active" : "");
    c.innerHTML = `<span class="em">${s.emoji}</span>${s.name}`;
    c.title = s.desc;
    c.addEventListener("click", () => {
      selStyle = raw.id;
      localStorage.setItem("comfyagent_style", s.id);
      box.querySelectorAll(".style-chip").forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
    });
    box.appendChild(c);
  }
}

/* 预估提示随所选工作流动态化（est_min/tier 由服务端注入） */
function updateHint() {
  const sel = $("#c-wf");
  const hint = $("#c-hint");
  if (!sel || !hint) return;
  const wf = workflows.find((w) => (w.id || w.name) === sel.value);
  if (!wf || wf.est_min == null) {
    hint.innerHTML = `<span class="dot2"></span>${mode === "video" ? VIDEO_HINT() : IMAGE_HINT()}`;
    return;
  }
  if (wf.tier === "draft") {
    hint.innerHTML = `<span class="dot2"></span>${tf("create.hint.draft", wf.est_min)}`;
  } else {
    hint.innerHTML = `<span class="dot2"></span>${tf("create.hint.est", mode === "video" ? "H3 W4A8 · 640×352 · ≈5s · 4步 · 原生音频" : "Flux 文生图 · 20步", wf.est_min)}`;
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
  sel.addEventListener("change", updateHint);
  const fits = workflows.filter((w) => mode === "video"
    ? /H3/.test(w.name) : !/H3/.test(w.name));
  sel.innerHTML = "";
  for (const wf of fits) {
    const o = document.createElement("option");
    o.value = wf.id || wf.name;
    o.textContent = wfLabel(wf);
    sel.appendChild(o);
  }
  const remembered = loadParams()["wf_" + mode];
  sel.value = remembered && fits.find((w) => (w.id || w.name) === remembered)
    ? remembered : (mode === "video" ? "h3-t2v" : "builtin-flux");
  if (!sel.value) sel.selectedIndex = 0;
  sel.onchange = () => saveParams({ ["wf_" + mode]: sel.value });
  $("#c-size-box").style.display = mode === "video" ? "none" : "";
  $("#c-hint").innerHTML = `<span class="dot2"></span>${mode === "video" ? VIDEO_HINT() : IMAGE_HINT()}`;
}

async function loadWorkflows() {
  const r = await api("/api/workflows");
  if (!r.ok) return;
  workflows = r.workflows;
  applyMode();
}

async function create() {
  const promptText = $("#c-prompt").value.trim();
  if (!promptText) { toast(t("err.no.prompt"), "err"); $("#c-prompt").focus(); return; }
  if (mode === "video" && selCount > 2 && !(await uiConfirm(tf("misc.confirm.video.count", selCount, Math.ceil(8.5 * selCount)), { danger: false }))) return;
  const sel = $("#c-wf");
  const wf = workflows.find((w) => (w.id || w.name) === sel.value);
  if (!wf) { toast(t("err.no.workflow"), "err"); return; }
  // 角色锁定串：追加到描述后一起增强，保证角色一致性
  const charObj = characters.find((c) => c.id === $("#c-char").value);
  const baseText = promptText + (charObj && charObj.lock ? "，" + charObj.lock : "");
  // 中文 → 英文增强（风格感知，可开关）
  let submitText = baseText;
  let styleParams = null;
  const styleObj = styles.find((s) => s.id === selStyle);
  if ($("#c-translate").classList.contains("active")) {
    const btn = $("#c-go");
    btn.disabled = true; btn.querySelector("span").textContent = t("st.translating");
    try {
      const en = await api("/api/enhance_prompt", {
        method: "POST", body: { text: promptText, style: selStyle, mode },
      });
      if (en.ok && en.english) {
        submitText = en.english;
        const pv = $("#c-en-preview");
        pv.innerHTML = `<span class="en-tag">EN（${en.engine}${styleObj ? " · " + styleView(styleObj).name : ""}）→</span>${en.english}<button class="kv-copy en-copy" data-copy="${en.english.replace(/"/g, "&quot;")}">${t("lb.copy")}</button>`;
        pv.hidden = false;
        if (en.note) toast(en.note, "err");
      } else {
        toast(en.error || t("err.translate.fail"), "err");
      }
    } finally {
      btn.disabled = false; btn.querySelector("span").textContent = t("act.generate");
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
  go.disabled = true; go.querySelector("span").textContent = t("st.submitting");
  try {
    const r = await api("/api/prompt", {
      method: "POST",
      body: { name: t("name.create.prefix") + promptText.slice(0, 16), prompt: wf.api, times: selCount, seed,
              overrides: { text, ...(hasLatentSize ? { width: w, height: h } : {}) },
              params: styleParams },
    });
    r.ok ? toast(r.msg + (hasLatentSize ? "" : t("video.mode.warn")), "ok") : toast(r.msg || r.error, "err");
    if (r.ok) $("#c-seed").value = "";
  } finally {
    go.disabled = false; go.querySelector("span").textContent = t("act.generate");
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
    box.innerHTML = `<div class="muted" style="padding:30px 0">${t("empty.feed")}</div>`;
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
        <button class="g-act" data-act="rerun" title="${t("act.rerun")}">↻</button>
        <button class="g-act" data-act="archive" title="${t("lb.archive")}">◈</button>
        <button class="g-act" data-act="download" title="${t("lb.download")}">↓</button>
      </div>
    </div>
    <span class="g-badge">${it.kind === "video" ? t("gallery.video") : t("gallery.image")}${it.w ? " · " + it.w + "×" + it.h : ""}</span>
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
    if (r.ok) { toast(t("toast.archived") + r.note, "ok"); const a = document.createElement("a"); a.href = r.uri; a.click(); }
    else toast(r.error || t("toast.archive.fail"), "err");
  });
  card.querySelector('[data-act="rerun"]')?.addEventListener("click", async (e) => {
    e.stopPropagation();
    const meta = await api(`/api/media/meta?path=${encodeURIComponent(it.path)}`);
    if (!meta.ok || !meta.prompt) { toast(t("err.no.embed"), "err"); return; }
    const r = await api("/api/prompt", { method: "POST", body: { name: t("name.rerun.prefix") + it.name, prompt: meta.prompt } });
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
  sel.innerHTML = `<option value="">${t("opt.none")}</option>` + characters.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  if (keep && characters.find((c) => c.id === keep)) sel.value = keep;
  sel.onchange = () => saveParams({ char: sel.value });
}
