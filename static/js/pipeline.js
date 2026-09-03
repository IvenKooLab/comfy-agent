/* pipeline.js — 产线：批次（脚本解析/排队/重试/拼接）+ 角色资产库 */
import { $, $$, api, toast, mediaUrl } from "./app.js";
import { t, tf } from "./i18n.js";

let batches = [];
let cur = null;          // 当前批次对象
let characters = [];
let curChar = null;

/* ---------- 画廊选图器（关键帧/参考图共用） ---------- */
let pickerCb = null;

function openPicker(title, cb) {
  pickerCb = cb;
  $("#picker-title").textContent = title;
  $("#picker").hidden = false;
  $("#picker-search").value = "";
  loadPicker("");
}

async function loadPicker(q) {
  const r = await api("/api/gallery");
  if (!r.ok) return;
  const items = r.items.filter((i) => i.kind === "image" && (!q || i.name.toLowerCase().includes(q)));
  const grid = $("#picker-grid");
  grid.innerHTML = items.length ? "" : `<div class="muted" style="grid-column:1/-1;padding:20px">${t("empty.gallery.search")}</div>`;
  for (const it of items.slice(0, 60)) {
    const el = document.createElement("div");
    el.className = "tpl-card";
    el.innerHTML = `<div class="tpl-thumb" style="aspect-ratio:3/4"><img src="${mediaUrl(it.path, { thumb: "1" })}" style="width:100%;height:100%;object-fit:cover">
      <div class="tpl-badges"><span class="tpl-badge">${it.w ? it.w + "×" + it.h : "IMG"}</span></div></div>
      <div class="tpl-info"><div class="tpl-title" title="${it.path}">${it.name}</div></div>`;
    el.addEventListener("click", () => { $("#picker").hidden = true; pickerCb && pickerCb(it.path); });
    grid.appendChild(el);
  }
}

export function initPipeline() {
  $("#picker-close").addEventListener("click", () => { $("#picker").hidden = true; });
  $("#picker-search").addEventListener("input", (e) => loadPicker(e.target.value.trim().toLowerCase()));
  $("#picker").addEventListener("click", (e) => { if (e.target.id === "picker") $("#picker").hidden = true; });
  $("#pl-import").addEventListener("click", () => { $("#pl-import-box").hidden = !$("#pl-import-box").hidden; });
  $("#pl-new").addEventListener("click", () => newBatch());
  $("#pl-parse").addEventListener("click", parseImport);
  $("#pl-save").addEventListener("click", saveBatch);
  $("#pl-run").addEventListener("click", runBatch);
  $("#pl-run-draft").addEventListener("click", () => runBatch(true));
  $("#pl-concat").addEventListener("click", concatBatch);
  $("#pl-del").addEventListener("click", delBatch);
  $("#pl-episodes").addEventListener("click", toggleEpisodes);
  $("#pl-scenes").addEventListener("click", () => {
    const box = $("#scene-editor");
    if (box) box.hidden = !box.hidden;
  });
  $("#char-new").addEventListener("click", () => { curChar = null; $("#char-editor").hidden = false; $("#char-name").value = ""; $("#char-lock").value = ""; $("#char-ref").value = ""; updateRefPreview(null); });
  $("#char-pick").addEventListener("click", () => openPicker(t("pick.char.refs"), (path) => {
    let refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
    if (!refs.includes(path)) refs.push(path);
    refs = refs.slice(0, 4);
    $("#char-ref").dataset.refs = refs.join("|");
    $("#char-ref").value = refs[0] || "";
    updateRefPreview(path);
    renderCharThumbs(refs);
  }));
  $("#char-pick-clear").addEventListener("click", () => { $("#char-ref").value = ""; updateRefPreview(null); });
  $("#char-save").addEventListener("click", saveChar);
  $("#char-del").addEventListener("click", delChar);
  initSceneHandlers();
  let syncTimer = null;
  new MutationObserver(() => {
    const active = $("#view-pipeline").classList.contains("active");
    if (active) { refresh(); loadChars(); loadScenes(); }
    if (active && !syncTimer) {
      syncTimer = setInterval(async () => {
        if (!$("#lightbox").hidden) return;
        await api("/api/batches/sync", { method: "POST", body: {} });
        if (cur && cur.id) {
          const r = await api("/api/batches/get", { method: "POST", body: { id: cur.id } });
          if (r.ok) { const before = JSON.stringify(cur.items.map(i=>i.status)); cur = r.batch;
            if (JSON.stringify(cur.items.map(i=>i.status)) !== before) renderItems(); refresh(); }
        } else refresh();
      }, 8000);
    }
    if (!active && syncTimer) { clearInterval(syncTimer); syncTimer = null; }
  }).observe($("#view-pipeline"), { attributes: true, attributeFilter: ["class"] });
}

async function refresh() {
  const r = await api("/api/batches");
  if (!r.ok) return;
  batches = r.batches;
  const box = $("#pl-list");
  box.innerHTML = "";
  const add = document.createElement("div");
  add.className = "wf-add"; add.textContent = t("pl.import.batch");
  add.addEventListener("click", () => { $("#pl-import-box").hidden = false; $("#pl-import-text").focus(); });
  box.appendChild(add);
  for (const b of batches) {
    const el = document.createElement("div");
    el.className = "wf-item" + (cur && cur.id === b.id ? " active" : "");
    el.innerHTML = `<div class="t">${b.name}</div>
      <div class="m"><span>${b.total}${t("unit.shots")}</span><span>✓${b.done} ✗${b.failed}</span></div>`;
    el.addEventListener("click", async () => { await openBatch(b.id); });
    box.appendChild(el);
  }
  if (cur) await renderBatch();
}

async function openBatch(id) {
  const r = await api("/api/batches/get", { method: "POST", body: { id } });
  if (!r.ok) { toast(r.error, "err"); return; }
  cur = r.batch;
  await api("/api/batches/sync", { method: "POST", body: {} });  // 刷新排队中状态
  const r2 = await api("/api/batches/get", { method: "POST", body: { id } });
  if (r2.ok) cur = r2.batch;
  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = cur.name;
  const mins = (cur.items || []).filter((i) => i.duration).reduce((a, i) => a + i.duration, 0);
  const done = (cur.items || []).filter((i) => i.status === "success").length;
  $("#pl-ledger").textContent = tf("pl.ledger", mins.toFixed(1), done, cur.items.length);
  await fillWfSelect();
  $("#pl-wf").value = cur.workflow_id || "h3-t2v";
  renderItems();
  refresh();
}

async function fillWfSelect() {
  const r = await api("/api/workflows");
  const sel = $("#pl-wf");
  if (!r.ok) return;
  sel.innerHTML = r.workflows.map((w) => `<option value="${w.id || ""}">${w.name}</option>`).join("");
  sel.value = cur.workflow_id || "h3-t2v";
}

function renderItems() {
  const box = $("#pl-items");
  const draftBtn = $("#pl-run-draft");
  if (draftBtn) draftBtn.hidden = !cur || !DRAFT_MAP_FE[cur.workflow_id];
  if (!cur || !cur.items || !cur.items.length) {
    box.innerHTML = `<div class="muted" style="padding:24px 0">${t("empty.batch")}<div style="margin-top:10px"><button class="btn sm primary" id="pl-empty-new">${t("pl.new")}</button></div></div>`;
    $("#pl-empty-new")?.addEventListener("click", newBatch);
    return;
  }
  const stMap = { success: [t("status.success"), "success"], error: [t("status.error"), "error"], queued: ["⏳ " + t("status.queued"), "queued"] };
  box.innerHTML = cur.items.map((it, i) => {
    const [txt, cls] = stMap[it.status] || [t("pl.notqueued"), ""];
    const ff = it.first_frame
      ? `<button class="btn sm pl-ff set" data-i="${i}" title="${it.first_frame}">${t("pl.ff.set")}</button>`
      : `<button class="btn sm ghost pl-ff" data-i="${i}">${t("pl.ff")}</button>`;
    const prio = it.priority
      ? `<button class="btn sm pl-prio set" data-i="${i}" title="${t("pl.prio.on.tip")}">⏫</button>`
      : `<button class="btn sm ghost pl-prio" data-i="${i}" title="${t("pl.prio.tip")}">⏫</button>`;
    const retryN = it.retry_count ? ` <span class="muted">↻${it.retry_count}</span>` : "";
    const chain = i > 0 ? `<button class="btn sm ghost pl-chain" data-i="${i}" title="${t("pl.chain.tip")}">↳</button>` : "";
    return `<div class="pl-item">
      <span class="run-status ${cls}">${txt}</span>
      <input class="input pl-item-name" data-i="${i}" value="${it.name.replace(/"/g, "&quot;")}">
      ${ff}
      ${prio}
      ${chain}
      <button class="btn sm ghost pl-retry" data-i="${i}" title="${t("pl.retry.one")}">↻</button>
    </div>
    <textarea class="input pl-prompt-edit" data-i="${i}" rows="2">${it.prompt.replace(/"/g, "&quot;").replace(/</g, "&lt;")}</textarea>`;
  }).join("");
  box.querySelectorAll(".pl-item-name").forEach((inp) => inp.addEventListener("change", (e) => {
    cur.items[+e.target.dataset.i].name = e.target.value; saveBatch(true);
  }));
  box.querySelectorAll(".pl-ff").forEach((b) => b.addEventListener("click", () => {
    const i = +b.dataset.i;
    if (cur.items[i].first_frame && !confirm(t("pl.ff.clear"))) { /* 保留可重选 */ }
    openPicker(tf("pick.ff", cur.items[i].name), (path) => {
      cur.items[i].first_frame = path;
      saveBatch(true);
      renderItems();
      toast(t("pl.ff.done"), "ok");
    });
  }));
  box.querySelectorAll(".pl-prompt-edit").forEach((ta) => ta.addEventListener("change", (e) => {
    cur.items[+e.target.dataset.i].prompt = e.target.value;
    saveBatch(true);
    toast(t("toast.prompt.updated"), "ok");
  }));
  box.querySelectorAll(".pl-retry").forEach((b) => b.addEventListener("click", async () => {
    const i = +b.dataset.i;
    const r = await api("/api/batches/retry", { method: "POST", body: { id: cur.id, index: i } });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    if (r.ok && r.batch) { cur = r.batch; renderItems(); refresh(); }
  }));
  box.querySelectorAll(".pl-chain").forEach((b) => b.addEventListener("click", () => chainFromPrev(+b.dataset.i)));
  box.querySelectorAll(".pl-prio").forEach((b) => b.addEventListener("click", () => {
    const it2 = cur.items[+b.dataset.i];
    it2.priority = !it2.priority;
    saveBatch(true);
    renderItems();
  }));
}

/* 草稿档映射与预估（分钟/镜，与研究实测一致）；成片档 8.5 为保守值 */
const DRAFT_MAP_FE = { "h3-t2v": "h3-t2v-t8draft", "h3-i2v": "h3-i2v-t8draft" };
const DRAFT_EST = { "h3-t2v": 2.7, "h3-i2v": 4.3 };

/* 镜头接龙：抽上一镜（最近一个成功且带输出的）末帧，设为本镜 i2v 首帧 */
async function chainFromPrev(i) {
  const prev = (cur.items || []).slice(0, i).reverse().find((it) => it.status === "success" && it.output);
  if (!prev) { toast(t("pl.chain.none"), "err"); return; }
  const r = await api("/api/video/last_frame", { method: "POST", body: { path: prev.output } });
  if (!r.ok) { toast(r.error || t("pl.chain.fail"), "err"); return; }
  cur.items[i].first_frame = r.frame;
  saveBatch(true);
  renderItems();
  toast(t("pl.chain.done"), "ok");
}

/* ---------- 导入/解析 ---------- */
async function parseImport() {
  const text = $("#pl-import-text").value;
  if (!text.trim()) { toast(t("pl.paste.first"), "err"); return; }
  const r = await api("/api/batches/parse", { method: "POST", body: { text } });
  if (!r.ok || !r.items.length) { toast(t("pl.parse.fail"), "err"); return; }
  cur = cur && cur.items && cur.items.length ? cur : { id: null, name: t("pl.newbatch"), workflow_id: "h3-t2v", items: [] };
  cur.items = r.items.map((it) => ({ ...it, status: null }));
  $("#pl-import-box").hidden = true;
  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = $("#pl-name").value || cur.name;
  await fillWfSelect();
  renderItems();
  toast(tf("pl.parsed", r.items.length), "ok");
}

async function newBatch() {
  cur = { id: null, name: t("pl.newbatch"), workflow_id: "h3-t2v", items: [] };
  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = cur.name;
  await fillWfSelect();
  renderItems();
}

/* ---------- 保存/运行/拼接/删除 ---------- */
async function saveBatch(silent) {
  if (!cur) return;
  cur.name = $("#pl-name").value.trim() || cur.name;
  cur.workflow_id = $("#pl-wf").value;
  const r = await api("/api/batches/save", { method: "POST", body: cur });
  if (r.ok) {
    cur.id = r.id;
    if (!silent) toast(t("pl.saved"), "ok");
    refresh();
  } else if (!silent) toast(r.error || t("toast.save.fail"), "err");
}

async function runBatch(draft = false) {
  if (!cur) return;
  await saveBatch(true);
  if (!cur.items.length) { toast(t("empty.batch"), "err"); return; }
  const est = draft ? (DRAFT_EST[cur.workflow_id] || 3) : 8.5;
  if (!confirm(draft ? tf("pl.run.draft.confirm", cur.items.length, Math.ceil(cur.items.length * est))
                     : tf("pl.queue.all", cur.items.length))) return;
  const r = await api("/api/batches/run", { method: "POST", body: { id: cur.id, draft } });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) { await openBatch(cur.id); setIntervalChecks(); }
}

let concatBusy = false;
async function concatBatch() {
  if (concatBusy) return;
  const outs = (cur?.items || []).filter((i) => i.status === "success" && i.output).map((i) => i.output);
  if (outs.length < 2) { toast(t("pl.concat.few"), "err"); return; }
  if (!confirm(tf("pl.concat.ask", outs.length))) return;
  concatBusy = true;
  toast(t("pl.concat.doing"), "");
  const bgm = $("#pl-bgm") ? $("#pl-bgm").value.trim() : "";
  const vol = $("#pl-bgm-vol") ? parseFloat($("#pl-bgm-vol").value) || 0.25 : 0.25;
  const r = await api("/api/concat", { method: "POST", body: { paths: outs, name: cur.name, bgm, bgm_volume: vol } });
  concatBusy = false;
  r.ok ? toast(r.msg + t("st.in.gallery"), "ok") : toast(r.error, "err");
}

async function delBatch() {
  if (!cur || !confirm(tf("misc.confirm.delete.batch", cur.name))) return;
  await api("/api/batches/delete", { method: "POST", body: { id: cur.id } });
  cur = null; $("#pl-detail-head").hidden = true; $("#pl-items").innerHTML = `<div class="muted">${t("pl.deleted")}</div>`;
  refresh();
}

function setIntervalChecks() { /* 状态由 openBatch 内 sync + 手动刷新；SSE 也会触发 */ }

/* ---------- 角色资产库 ---------- */
async function loadChars() {
  const r = await api("/api/characters");
  if (!r.ok) return;
  characters = r.characters;
  const box = $("#char-list");
  box.innerHTML = characters.length
    ? characters.map((c) => `<div class="note-item" data-id="${c.id}"><span class="nm">🧑‍🎤 ${c.name}</span><span class="meta">${(c.lock || "").length}${t("unit.lock")}</span></div>`).join("")
    : `<div class="muted">${t("empty.chars")}</div>`;
  box.querySelectorAll(".note-item").forEach((el) => el.addEventListener("click", () => editChar(el.dataset.id)));
  document.dispatchEvent(new CustomEvent("characters-updated", { detail: characters }));
}

function editChar(id) {
  const c = characters.find((x) => x.id === id);
  if (!c) return;
  curChar = c;
  $("#char-editor").hidden = false;
  $("#char-name").value = c.name; $("#char-lock").value = c.lock || ""; $("#char-ref").value = c.ref || "";
  updateRefPreview(c.ref);
  renderCharThumbs(c.refs && c.refs.length ? c.refs : (c.ref ? [c.ref] : []));
}

function renderCharThumbs(refs) {
  const box = $("#char-refs-thumbs");
  if (!box) return;
  box.innerHTML = (refs || []).map((r, i) =>
    `<div style="position:relative"><img src="/api/media?path=${encodeURIComponent(r)}&thumb=1" style="height:60px;border-radius:8px">
     <button class="btn sm danger ghost" data-i="${i}" style="position:absolute;top:-6px;right:-6px;padding:0 6px">✕</button></div>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
    refs.splice(+b.dataset.i, 1);
    $("#char-ref").dataset.refs = refs.join("|");
    $("#char-ref").value = refs[0] || "";
    renderCharThumbs(refs);
  }));
}

function updateRefPreview(path) {
  const img = $("#char-ref-preview");
  if (path) { img.src = "/api/media?path=" + encodeURIComponent(path) + "&thumb=1"; img.style.display = ""; }
  else img.style.display = "none";
}

async function saveChar() {
  const refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
  const body = { name: $("#char-name").value.trim(), lock: $("#char-lock").value,
                 ref: refs[0] || $("#char-ref").value.trim(), refs };
  if (!body.name) { toast(t("err.char.name"), "err"); return; }
  if (curChar) body.id = curChar.id;
  const r = await api("/api/characters/save", { method: "POST", body });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) { curChar = r.character; loadChars(); }
}

async function delChar() {
  if (!curChar) return;
  if (!confirm(tf("misc.confirm.delete.char", curChar.name))) return;
  await api("/api/characters/delete", { method: "POST", body: { id: curChar.id } });
  curChar = null; $("#char-editor").hidden = true; loadChars();
}


/* ---------- 场景库 ---------- */
let scenes = [];
let curScene = null;

async function loadScenes() {
  const r = await api("/api/scenes");
  if (!r.ok) return;
  scenes = r.scenes;
  const box = $("#scene-list");
  if (!box) return;
  box.innerHTML = scenes.length
    ? scenes.map((s) => `<div class="note-item" data-id="${s.id}"><span class="nm">🌐 ${s.name}</span><span class="meta">${(s.tokens || "").length}${t("unit.words")}</span></div>`).join("")
    : `<div class="muted">${t("empty.nodes")}</div>`;
  box.querySelectorAll(".note-item").forEach((el) => el.addEventListener("click", () => editScene(el.dataset.id)));
}

function editScene(id) {
  const s = scenes.find((x) => x.id === id);
  if (!s) return;
  curScene = s;
  $("#scene-editor").hidden = false;
  $("#scene-name").value = s.name;
  $("#scene-desc").value = s.desc || "";
  $("#scene-tokens").value = s.tokens || "";
}

function initSceneHandlers() {
  $("#scene-new").addEventListener("click", () => {
    curScene = null; $("#scene-editor").hidden = false;
    $("#scene-name").value = ""; $("#scene-desc").value = ""; $("#scene-tokens").value = "";
  });
  $("#scene-save").addEventListener("click", async () => {
    const body = { name: $("#scene-name").value.trim(), desc: $("#scene-desc").value, tokens: $("#scene-tokens").value };
    if (!body.name) { toast(t("err.scene.name"), "err"); return; }
    if (curScene) body.id = curScene.id;
    const r = await api("/api/scenes/save", { method: "POST", body });
    toast(r.ok ? t("scene.saved") : r.error, r.ok ? "ok" : "err");
    loadScenes();
  });
  $("#scene-del").addEventListener("click", async () => {
    if (!curScene || !confirm(t("misc.confirm.scene"))) return;
    await api("/api/scenes/delete", { method: "POST", body: { id: curScene.id } });
    curScene = null; $("#scene-editor").hidden = true; loadScenes();
  });
}

/* ---------- 集数聚合视图 ---------- */
let episodesVisible = false;

function toggleEpisodes() {
  episodesVisible = !episodesVisible;
  $("#pl-episodes-view").hidden = !episodesVisible;
  $("#pl-detail-head").hidden = episodesVisible;
  $("#pl-items").innerHTML = episodesVisible ? "" : `<div class="muted">${t("empty.batches")}</div>`;
  if (episodesVisible) renderEpisodes();
}

async function renderEpisodes() {
  const r = await api("/api/batches/episodes");
  if (!r.ok) return;
  const box = $("#pl-items");
  box.innerHTML = r.episodes.length
    ? `<div class="card pad"><h3 style="font-size:13px;margin-bottom:10px">${t("pl.epagg")}</h3>
       ${r.episodes.map((e) => `<div class="pl-item">
           <b>${e.name}</b> · ${e.total}${t("unit.shots")} · ✓${e.done} ✗${e.failed} · ⏱${e.gpu_minutes.toFixed(1)}min
         </div>`).join("")}</div>`
    : `<div class="muted">${t("pl.nobatch")}</div>`;
}

/* ---------- 字幕烧入 ---------- */
function initSubtitleBurn() {
  const subBtn = $("#pl-subtitle");
  if (!subBtn) return;
  subBtn.addEventListener("click", async () => {
    const video = prompt(t("sub.video.path"));
    const srt = prompt(t("sub.srt.path"));
    if (!video || !srt) return;
    const r = await api("/api/subtitle_burn", { method: "POST", body: { video, srt_path: srt } });
    toast(r.ok ? t("sub.done") + r.output : r.error, r.ok ? "ok" : "err");
  });
  subBtn.click();
}
