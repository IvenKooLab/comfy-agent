/* pipeline.js — 产线：批次（脚本解析/排队/重试/拼接）+ 角色资产库 */
import { $, $$, api, toast, mediaUrl } from "./app.js";

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
  grid.innerHTML = items.length ? "" : `<div class="muted" style="grid-column:1/-1;padding:20px">没有匹配的图片</div>`;
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
  $("#pl-concat").addEventListener("click", concatBatch);
  $("#pl-del").addEventListener("click", delBatch);
  $("#pl-bgm-vol").addEventListener("change", () => {}); // 占位保持布局
  $("#char-new").addEventListener("click", () => { curChar = null; $("#char-editor").hidden = false; $("#char-name").value = ""; $("#char-lock").value = ""; $("#char-ref").value = ""; updateRefPreview(null); });
  $("#char-pick").addEventListener("click", () => openPicker("选择角色参考图（可多选，最多4张）", (path) => {
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
  let syncTimer = null;
  new MutationObserver(() => {
    const active = $("#view-pipeline").classList.contains("active");
    if (active) { refresh(); loadChars(); }
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
  add.className = "wf-add"; add.textContent = "＋ 从脚本导入批次";
  add.addEventListener("click", () => { $("#pl-import-box").hidden = false; $("#pl-import-text").focus(); });
  box.appendChild(add);
  for (const b of batches) {
    const el = document.createElement("div");
    el.className = "wf-item" + (cur && cur.id === b.id ? " active" : "");
    el.innerHTML = `<div class="t">${b.name}</div>
      <div class="m"><span>${b.total} 镜</span><span>✓${b.done} ✗${b.failed}</span></div>`;
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
  $("#pl-ledger").textContent = `⏱ GPU 已用 ${mins.toFixed(1)} 分钟 · 成功 ${done}/${cur.items.length}`;
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
  if (!cur || !cur.items || !cur.items.length) { box.innerHTML = `<div class="muted">批次为空</div>`; return; }
  const stMap = { success: ["✓ 成功", "success"], error: ["✗ 失败", "error"], queued: ["⏳ 排队", "queued"] };
  box.innerHTML = cur.items.map((it, i) => {
    const [txt, cls] = stMap[it.status] || ["— 未排队", ""];
    const ff = it.first_frame
      ? `<button class="btn sm pl-ff set" data-i="${i}" title="${it.first_frame}">🖼 已设关键帧</button>`
      : `<button class="btn sm ghost pl-ff" data-i="${i}">🖼 关键帧</button>`;
    const retryN = it.retry_count ? ` <span class="muted">↻${it.retry_count}</span>` : "";
    return `<div class="pl-item">
      <span class="run-status ${cls}">${txt}</span>
      <input class="input pl-item-name" data-i="${i}" value="${it.name.replace(/"/g, "&quot;")}">
      ${ff}
      <button class="btn sm ghost pl-retry" data-i="${i}" title="单独重试这一镜">↻</button>
    </div>
    <textarea class="input pl-prompt-edit" data-i="${i}" rows="2">${it.prompt.replace(/"/g, "&quot;").replace(/</g, "&lt;")}</textarea>`;
  }).join("");
  box.querySelectorAll(".pl-item-name").forEach((inp) => inp.addEventListener("change", (e) => {
    cur.items[+e.target.dataset.i].name = e.target.value; saveBatch(true);
  }));
  box.querySelectorAll(".pl-ff").forEach((b) => b.addEventListener("click", () => {
    const i = +b.dataset.i;
    if (cur.items[i].first_frame && !confirm("清除该镜头的关键帧？")) { /* 保留可重选 */ }
    openPicker(`选择镜头「${cur.items[i].name}」的首帧图（i2v 锁脸）`, (path) => {
      cur.items[i].first_frame = path;
      saveBatch(true);
      renderItems();
      toast("关键帧已设置（提交时自动注入 i2v 首帧）", "ok");
    });
  }));
  box.querySelectorAll(".pl-prompt-edit").forEach((ta) => ta.addEventListener("change", (e) => {
    cur.items[+e.target.dataset.i].prompt = e.target.value;
    saveBatch(true);
    toast("提示词已更新", "ok");
  }));
  box.querySelectorAll(".pl-retry").forEach((b) => b.addEventListener("click", async () => {
    const i = +b.dataset.i;
    const r = await api("/api/batches/retry", { method: "POST", body: { id: cur.id, index: i } });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    if (r.ok && r.batch) { cur = r.batch; renderItems(); refresh(); }
  }));
}

/* ---------- 导入/解析 ---------- */
async function parseImport() {
  const text = $("#pl-import-text").value;
  if (!text.trim()) { toast("先粘贴脚本内容", "err"); return; }
  const r = await api("/api/batches/parse", { method: "POST", body: { text } });
  if (!r.ok || !r.items.length) { toast("没解析出镜头。支持 ### SHOTxx【画风】+ text 代码块，或「镜头名 | 提示词」行", "err"); return; }
  cur = cur && cur.items && cur.items.length ? cur : { id: null, name: "新批次", workflow_id: "h3-t2v", items: [] };
  cur.items = r.items.map((it) => ({ ...it, status: null }));
  $("#pl-import-box").hidden = true;
  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = $("#pl-name").value || cur.name;
  await fillWfSelect();
  renderItems();
  toast(`解析出 ${r.items.length} 个镜头，检查无误后点「保存」`, "ok");
}

async function newBatch() {
  cur = { id: null, name: "新批次", workflow_id: "h3-t2v", items: [] };
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
    if (!silent) toast("批次已保存", "ok");
    refresh();
  } else if (!silent) toast(r.error || "保存失败", "err");
}

async function runBatch() {
  if (!cur) return;
  await saveBatch(true);
  if (!cur.items.length) { toast("批次为空", "err"); return; }
  if (!confirm(`把 ${cur.items.length} 个镜头全部排队？（H3 视频每条约 8.5 分钟）`)) return;
  const r = await api("/api/batches/run", { method: "POST", body: { id: cur.id } });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) { await openBatch(cur.id); setIntervalChecks(); }
}

let concatBusy = false;
async function concatBatch() {
  if (concatBusy) return;
  const outs = (cur?.items || []).filter((i) => i.status === "success" && i.output).map((i) => i.output);
  if (outs.length < 2) { toast("成功且带输出的镜头不足 2 个", "err"); return; }
  if (!confirm(`把 ${outs.length} 段镜头按顺序拼接成片？`)) return;
  concatBusy = true;
  toast("拼接中…", "");
  const bgm = $("#pl-bgm") ? $("#pl-bgm").value.trim() : "";
  const vol = $("#pl-bgm-vol") ? parseFloat($("#pl-bgm-vol").value) || 0.25 : 0.25;
  const r = await api("/api/concat", { method: "POST", body: { paths: outs, name: cur.name, bgm, bgm_volume: vol } });
  concatBusy = false;
  r.ok ? toast(r.msg + "（已进画廊）", "ok") : toast(r.error, "err");
}

async function delBatch() {
  if (!cur || !confirm(`删除批次「${cur.name}」？`)) return;
  await api("/api/batches/delete", { method: "POST", body: { id: cur.id } });
  cur = null; $("#pl-detail-head").hidden = true; $("#pl-items").innerHTML = `<div class="muted">已删除</div>`;
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
    ? characters.map((c) => `<div class="note-item" data-id="${c.id}"><span class="nm">🧑‍🎤 ${c.name}</span><span class="meta">${(c.lock || "").length}字锁定</span></div>`).join("")
    : `<div class="muted">还没有角色。新建一个，把角色锁定串存进来。</div>`;
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
  if (!body.name) { toast("角色名必填", "err"); return; }
  if (curChar) body.id = curChar.id;
  const r = await api("/api/characters/save", { method: "POST", body });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) { curChar = r.character; loadChars(); }
}

async function delChar() {
  if (!curChar) return;
  if (!confirm(`删除角色「${curChar.name}」？`)) return;
  await api("/api/characters/delete", { method: "POST", body: { id: curChar.id } });
  curChar = null; $("#char-editor").hidden = true; loadChars();
}
