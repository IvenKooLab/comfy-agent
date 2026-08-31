/* editor.js — 工作流可视化编辑器：SVG 节点图 + 参数检查器 + 导入导出 */
import { $, $$, api, toast, goto } from "./app.js";
import { t, tf, wfLabel } from "./i18n.js";

const NS = "http://www.w3.org/2000/svg";
const NODE_W = 195, HEAD_H = 26, ROW_H = 20, PORT_R = 5.5;

let workflows = [];
let cur = null;                 // {id,name,api,layout,builtin}
let objectInfo = null;
let view = { x: 40, y: 30, k: 1 };
let selected = null;
let snap = true;
let svg, gEdges, gNodes, gTemp;

/* ================= 初始化 ================= */
export function initEditor() {
  svg = $("#graph");
  gEdges = mk("g"); gNodes = mk("g"); gTemp = mk("g");
  svg.append(gEdges, gTemp, gNodes);
  svg.addEventListener("mousedown", onPanStart);
  svg.addEventListener("wheel", onWheel, { passive: false });
  svg.addEventListener("dblclick", onCanvasDblClick);
  document.addEventListener("keydown", (e) => {
    if (!$("#view-editor").classList.contains("active")) return;
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveWorkflow(); }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runWorkflow(); }
    if ((e.key === "Delete" || e.key === "Backspace") && selected && !isTyping(e.target)) delNode(selected);
  });
  $("#wf-save").addEventListener("click", saveWorkflow);
  $("#wf-run").addEventListener("click", runWorkflow);
  $("#wf-interrupt").addEventListener("click", async () => { await api("/api/interrupt", { method: "POST", body: {} }); });
  $("#wf-import").addEventListener("click", () => $("#wf-file").click());
  $("#wf-file").addEventListener("change", onImportFiles);
  $("#wf-export").addEventListener("click", exportApi);
  $("#cv-snap").addEventListener("click", () => { snap = !snap; $("#cv-snap").classList.toggle("on", snap); });
  $("#cv-add").addEventListener("click", (e) => openPalette(e.clientX - 300, e.clientY - 100));
  $("#cv-fit").addEventListener("click", fitView);
  $("#cv-zin").addEventListener("click", () => zoomBy(1.25));
  $("#cv-zout").addEventListener("click", () => zoomBy(0.8));
  $("#palette-search").addEventListener("input", renderPalette);
  document.addEventListener("mousedown", (e) => {
    const pal = $("#node-palette");
    if (!pal.hidden && !pal.contains(e.target) && e.target.id !== "cv-add") pal.hidden = true;
  });
  loadList().then(() => {
    validate();
    doPendingImport();
  });
}

function doPendingImport() {
  // 画廊/模板页跳转导入（API 格式 or UI 格式）
  const pend = localStorage.getItem("pendingImport");
  const pendUI = localStorage.getItem("pendingImportUI");
  if (pend) {
    localStorage.removeItem("pendingImport");
    try {
      const { api: a, name } = JSON.parse(pend);
      cur = { id: null, name: t("ed.fromimg") + (name || t("common.workflow")), api: a, layout: {}, builtin: false };
      afterLoad();
      toast(t("ed.loaded.img"), "ok");
    } catch { }
    return;
  }
  if (pendUI) {
    localStorage.removeItem("pendingImportUI");
    try {
      const { ui, name } = JSON.parse(pendUI);
      importUI(ui, name || t("ed.fromtpl"));
    } catch (err) { toast(t("ed.import.fail") + err.message, "err"); }
  }
}

/* 供模板库等外部模块触发导入 */
document.addEventListener("templates-import", () => doPendingImport());

const snapV = (v) => snap ? Math.round(v / 12) * 12 : v;

/* 校验：object_info 可用时给未知类型节点打 invalid 标 */
async function validate() {
  try {
    const r = await api("/api/object_info");
    if (!r.ok) return;
    objectInfo = r.object_info;
    for (const id of nodeIds()) {
      const ok = !!schemaOf(cur.api[id].class_type);
      gNodes.querySelector(`g[data-id="${CSS.escape(id)}"]`)?.classList.toggle("invalid", !ok);
    }
  } catch { /* ComfyUI 离线时跳过 */ }
}

const mk = (tag, attrs = {}) => {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};
const isTyping = (t) => ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ================= 工作流列表 ================= */
async function loadList(selectId) {
  const r = await api("/api/workflows");
  if (!r.ok) return;
  workflows = r.workflows;
  const box = $("#wf-list");
  box.innerHTML = "";
  const add = document.createElement("div");
  add.className = "wf-add"; add.textContent = t("editor.new");
  add.addEventListener("click", () => { cur = { id: null, name: t("ed.newwf"), api: {}, layout: {}, builtin: false }; afterLoad(); });
  box.appendChild(add);
  for (const wf of workflows) {
    const el = document.createElement("div");
    el.className = "wf-item" + (cur && cur.id === wf.id ? " active" : "");
    el.innerHTML = `<div class="t">${esc(wfLabel(wf))}</div>
      <div class="m"><span>${wf.builtin ? t("ed.builtin") : esc((wf.updated || "").slice(5))} · ${Object.keys(wf.api || {}).length}${t("unit.nodes")}</span>
      ${wf.builtin ? "" : `<span class="del" title="${t("act.delete")}">✕</span>`}</div>`;
    el.addEventListener("click", () => { cur = JSON.parse(JSON.stringify(wf)); afterLoad(); renderListSel(); });
    el.querySelector(".del")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm(tf("ed.del.ask", wf.name))) return;
      const rr = await api("/api/workflows/delete", { method: "POST", body: { id: wf.id } });
      rr.ok ? loadList() : toast(rr.error, "err");
    });
    box.appendChild(el);
  }
  if (selectId) renderListSel();
  if (!cur && workflows.length) { cur = JSON.parse(JSON.stringify(workflows[0])); afterLoad(); }
}
function renderListSel() {
  $$("#wf-list .wf-item").forEach((el, i) => el.classList.toggle("active", workflows[i] && workflows[i].id === cur?.id));
}
function afterLoad() {
  $("#wf-name").value = cur?.name || "";
  ensureLayout();
  selected = null;
  renderGraph();
  renderInspector();
  fitView();
}

/* ================= 布局与渲染 ================= */
function nodeIds() { return Object.keys(cur.api); }
function nextId() { return String(nodeIds().reduce((m, i) => Math.max(m, +i || 0), 0) + 1); }

function ensureLayout() {
  if (!cur.api) cur.api = {};
  if (!cur.layout) cur.layout = {};
  // 拓扑分层自动布局
  const ids = nodeIds();
  const level = {};
  const depth = (id, seen) => {
    if (level[id] != null) return level[id];
    if (seen.has(id)) return 0;
    seen.add(id);
    let d = 0;
    for (const v of Object.values(cur.api[id].inputs || {}))
      if (Array.isArray(v) && cur.api[v[0]]) d = Math.max(d, depth(String(v[0]), seen) + 1);
    level[id] = d;
    return d;
  };
  ids.forEach((id) => depth(id, new Set()));
  const perLevel = {};
  for (const id of ids) {
    if (cur.layout[id]) continue;
    const lv = level[id] || 0;
    perLevel[lv] = (perLevel[lv] || 0) + 1;
    cur.layout[id] = [40 + lv * 270, 40 + (perLevel[lv] - 1) * 170];
  }
}

function schemaOf(ct) { return objectInfo?.[ct] || null; }

function portDefs(id) {
  const node = cur.api[id];
  const s = schemaOf(node.class_type);
  const inputs = [], scalars = [];
  if (s) {
    const req = s.input?.required || {}, opt = s.input?.optional || {};
    for (const [name, def] of [...Object.entries(req), ...Object.entries(opt)]) {
      const t = Array.isArray(def) ? def[0] : "?";
      if (typeof t === "string" && /^[A-Z][A-Z_]*$/.test(t)) inputs.push({ name, type: t });
      else scalars.push({ name, def, type: typeof t === "string" ? t : (Array.isArray(t) ? "COMBO" : "?") });
    }
  } else {
    for (const [name, val] of Object.entries(node.inputs || {})) {
      if (Array.isArray(val)) inputs.push({ name, type: "LINK" });
      else scalars.push({ name, def: null, type: typeof val === "number" ? "NUMBER" : "STRING" });
    }
  }
  let outputs = [];
  if (s?.output) outputs = (s.output || []).map((t, i) => ({ slot: i, type: t }));
  else {
    let mx = 0;
    for (const n2 of nodeIds())
      for (const v of Object.values(cur.api[n2].inputs || {}))
        if (Array.isArray(v) && String(v[0]) === id) mx = Math.max(mx, v[1] || 0);
    outputs = [{ slot: 0, type: "?" }];
    if (mx > 0) outputs = Array.from({ length: mx + 1 }, (_, i) => ({ slot: i, type: "?" }));
  }
  return { inputs, scalars, outputs };
}

function nodeSize(id) {
  const { inputs, outputs } = portDefs(id);
  const rows = Math.max(inputs.length, outputs.length, 1);
  return { w: NODE_W, h: HEAD_H + rows * ROW_H + 12 };
}
const portXY = (id, which, i) => {
  const [x, y] = cur.layout[id] || [0, 0];
  const { h } = nodeSize(id);
  return { x: which === "out" ? x + NODE_W : x, y: y + HEAD_H + 12 + i * ROW_H };
};

function renderGraph() {
  gEdges.innerHTML = ""; gNodes.innerHTML = ""; gTemp.innerHTML = "";
  applyView();
  for (const id of nodeIds()) {
    const node = cur.api[id];
    const { w, h } = nodeSize(id);
    const { inputs, outputs } = portDefs(id);
    const g = mk("g", { class: "node-g" + (selected === id ? " selected" : ""), transform: `translate(${cur.layout[id][0]},${cur.layout[id][1]})` });
    g.dataset.id = id;
    const box = mk("rect", { class: "node-box", width: w, height: h, rx: 10 });
    const head = mk("rect", { class: "node-head", width: w, height: HEAD_H, rx: 10 });
    const ct = node.class_type || "?";
    const short = ct.split("/").pop();
    const title = mk("text", { class: "node-title", x: 9, y: 17 });
    title.textContent = short;
    g.append(box, head, title);
    if (ct.includes("/")) {
      const sub = mk("text", { class: "node-sub", x: w - 6, y: 17, "text-anchor": "end" });
      sub.textContent = ct.split("/").slice(0, -1).join("/");
      g.append(sub);
    }
    inputs.forEach((p, i) => {
      const { x: px, y: py } = { x: 0, y: HEAD_H + 12 + i * ROW_H };
      const linked = Array.isArray(node.inputs?.[p.name]);
      const c = mk("circle", { class: "port" + (linked ? " linked" : ""), cx: px, cy: py, r: PORT_R });
      c.dataset.id = id; c.dataset.port = p.name; c.dataset.kind = "in";
      const lab = mk("text", { class: "node-io-label", x: px + 10, y: py + 3 });
      lab.textContent = p.name;
      g.append(c, lab);
    });
    outputs.forEach((p, i) => {
      const py = HEAD_H + 12 + i * ROW_H;
      const c = mk("circle", { class: "port", cx: w, cy: py, r: PORT_R });
      c.dataset.id = id; c.dataset.slot = p.slot; c.dataset.kind = "out";
      const lab = mk("text", { class: "node-io-label", x: w - 10, y: py + 3, "text-anchor": "end" });
      lab.textContent = p.type === "?" ? `out${p.slot}` : p.type;
      g.append(c, lab);
    });
    g.addEventListener("mousedown", (e) => onNodeDown(e, id));
    g.addEventListener("click", (e) => { e.stopPropagation(); selectNode(id); });
    gNodes.appendChild(g);
  }
  // 连线（数据驱动）
  for (const id of nodeIds()) {
    for (const [iname, val] of Object.entries(cur.api[id].inputs || {})) {
      if (!Array.isArray(val) || !cur.api[val[0]]) continue;
      const src = String(val[0]);
      const outs = portDefs(src).outputs;
      const oi = outs.findIndex((o) => o.slot === (val[1] || 0));
      const a = portXY(src, "out", Math.max(oi, 0));
      const ins = portDefs(id).inputs;
      const ii = ins.findIndex((p) => p.name === iname);
      if (ii < 0) continue;
      const b = portXY(id, "in", ii);
      const path = mk("path", { class: "edge", d: edgePath(a, b) });
      path.addEventListener("click", (e) => {
        e.stopPropagation();
        if (confirm(tf("ed.unlink.ask", cur.api[src].class_type, iname))) {
          delete cur.api[id].inputs[iname];
          renderGraph();
        }
      });
      gEdges.appendChild(path);
    }
  }
}
const edgePath = (a, b) => `M${a.x},${a.y} C${a.x + 70},${a.y} ${b.x - 70},${b.y} ${b.x},${b.y}`;

function applyView() {
  gEdges.setAttribute("transform", `translate(${view.x},${view.y}) scale(${view.k})`);
  gNodes.setAttribute("transform", `translate(${view.x},${view.y}) scale(${view.k})`);
  gTemp.setAttribute("transform", `translate(${view.x},${view.y}) scale(${view.k})`);
}
const toWorld = (e) => {
  const r = svg.getBoundingClientRect();
  return { x: (e.clientX - r.left - view.x) / view.k, y: (e.clientY - r.top - view.y) / view.k };
};

/* ---------- 视图交互 ---------- */
function onPanStart(e) {
  if (e.target.closest(".node-g") || e.target.closest(".port")) return;
  selectNode(null);
  const start = { mx: e.clientX, my: e.clientY, vx: view.x, vy: view.y };
  svg.classList.add("panning");
  const move = (ev) => { view.x = start.vx + (ev.clientX - start.mx); view.y = start.vy + (ev.clientY - start.my); applyView(); };
  const up = () => { svg.classList.remove("panning"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
  document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
}
function onWheel(e) {
  e.preventDefault();
  const f = e.deltaY < 0 ? 1.12 : 0.89;
  const r = svg.getBoundingClientRect();
  const cx = e.clientX - r.left, cy = e.clientY - r.top;
  view.k = Math.min(2.5, Math.max(0.2, view.k * f));
  view.x = cx - (cx - view.x) * f; view.y = cy - (cy - view.y) * f;
  applyView();
}
function zoomBy(f) { view.k = Math.min(2.5, Math.max(0.2, view.k * f)); applyView(); }
function fitView() {
  const ids = nodeIds();
  if (!ids.length) { view = { x: 40, y: 30, k: 1 }; applyView(); return; }
  let x1 = 1e9, y1 = 1e9, x2 = -1e9, y2 = -1e9;
  for (const id of ids) {
    const [x, y] = cur.layout[id]; const { w, h } = nodeSize(id);
    x1 = Math.min(x1, x); y1 = Math.min(y1, y); x2 = Math.max(x2, x + w); y2 = Math.max(y2, y + h);
  }
  const r = svg.getBoundingClientRect();
  const k = Math.min(2, Math.max(0.25, Math.min((r.width - 60) / (x2 - x1), (r.height - 60) / (y2 - y1))));
  view = { k, x: 30 - x1 * k + (r.width - 60 - (x2 - x1) * k) / 2, y: 30 - y1 * k + (r.height - 60 - (y2 - y1) * k) / 2 };
  applyView();
}

/* ---------- 节点交互 ---------- */
function onNodeDown(e, id) {
  if (e.target.classList.contains("port")) { onPortDown(e, id, e.target); return; }
  if (e.button !== 0) return;
  e.stopPropagation();
  selectNode(id);
  const start = { mx: e.clientX, my: e.clientY, ox: cur.layout[id][0], oy: cur.layout[id][1] };
  const move = (ev) => {
    cur.layout[id] = [
      snapV(start.ox + (ev.clientX - start.mx) / view.k),
      snapV(start.oy + (ev.clientY - start.my) / view.k),
    ];
    const g = gNodes.querySelector(`g[data-id="${CSS.escape(id)}"]`);
    if (g) g.setAttribute("transform", `translate(${cur.layout[id][0]},${cur.layout[id][1]})`);
    renderEdgesOnly();
  };
  const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
  document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
}

function renderEdgesOnly() {
  gEdges.innerHTML = "";
  for (const id of nodeIds())
    for (const [iname, val] of Object.entries(cur.api[id].inputs || {})) {
      if (!Array.isArray(val) || !cur.api[val[0]]) continue;
      const src = String(val[0]);
      const oi = Math.max(portDefs(src).outputs.findIndex((o) => o.slot === (val[1] || 0)), 0);
      const a = portXY(src, "out", oi);
      const ii = portDefs(id).inputs.findIndex((p) => p.name === iname);
      if (ii < 0) continue;
      gEdges.appendChild(mk("path", { class: "edge", d: edgePath(a, portXY(id, "in", ii)) }));
    }
}

function onPortDown(e, id, portEl) {
  e.stopPropagation(); e.preventDefault();
  if (portEl.dataset.kind === "in") {
    // 点击已连接输入口 → 断开
    const iname = portEl.dataset.port;
    if (Array.isArray(cur.api[id].inputs?.[iname])) {
      delete cur.api[id].inputs[iname];
      renderGraph();
      return;
    }
    return;
  }
  // 从输出口拖出连线
  const slot = +portEl.dataset.slot;
  const a = portXY(id, "out", portDefs(id).outputs.findIndex((o) => o.slot === slot));
  const temp = mk("path", { class: "edge temp", d: "" });
  gTemp.appendChild(temp);
  const move = (ev) => {
    const w = toWorld(ev);
    temp.setAttribute("d", edgePath(a, w));
  };
  const up = (ev) => {
    temp.remove();
    document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up);
    const tgt = ev.target.closest?.(".port[data-kind='in']");
    if (tgt && tgt.dataset.id !== id) {
      cur.api[tgt.dataset.id].inputs[tgt.dataset.port] = [id, slot];
      renderGraph();
    }
  };
  document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
}

function selectNode(id) {
  selected = id;
  gNodes.querySelectorAll(".node-g").forEach((g) => g.classList.toggle("selected", g.dataset.id === id));
  renderInspector();
}
function delNode(id) {
  delete cur.api[id];
  delete cur.layout[id];
  for (const n2 of nodeIds())
    for (const [k, v] of Object.entries(cur.api[n2].inputs || {}))
      if (Array.isArray(v) && String(v[0]) === id) delete cur.api[n2].inputs[k];
  selected = null;
  renderGraph(); renderInspector();
}

/* ================= 检查器 ================= */
function renderInspector() {
  const empty = $("#inspector-empty"), body = $("#inspector-body");
  if (!selected) { empty.hidden = false; body.hidden = true; return; }
  empty.hidden = true; body.hidden = false;
  const node = cur.api[selected];
  const ct = node.class_type || "?";
  const { scalars, outputs } = portDefs(selected);
  const s = schemaOf(ct);
  let html = `<div class="insp-title">${esc(ct.split("/").pop())}</div>
    <div class="insp-nodeid">${tf("ed.insp.head", selected, Object.keys(node.inputs || {}).length, outputs.length)}</div>`;
  if (!s) html += `<div class="insp-warn">${t("ed.insp.warn")}</div>`;
  for (const f of scalars) {
    const val = node.inputs?.[f.name];
    const t = f.type;
    const label = `<label>${esc(f.name)}</label>`;
    if (t === "COMBO" || (Array.isArray(f.def?.[0]) )) {
      const opts = Array.isArray(f.def?.[0]) ? f.def[0] : [];
      const curv = val != null ? val : (opts[0] ?? "");
      html += `<div class="field">${label}<select data-f="${esc(f.name)}">` +
        opts.map((o) => `<option ${String(o) === String(curv) ? "selected" : ""}>${esc(o)}</option>`).join("") +
        (opts.length === 0 || !opts.includes(curv) ? `<option selected>${esc(curv)}</option>` : "") + `</select></div>`;
    } else if (t === "BOOLEAN") {
      html += `<div class="field">${label}<select data-f="${esc(f.name)}">
        <option value="true" ${val ? "selected" : ""}>true</option><option value="false" ${!val ? "selected" : ""}>false</option></select></div>`;
    } else if (t === "INT" || t === "FLOAT" || t === "NUMBER") {
      const isSeed = /seed/i.test(f.name);
      html += `<div class="field">${label}<div class="seed-row">
        <input class="input" type="number" step="${t === "FLOAT" ? "0.1" : "1"}" data-f="${esc(f.name)}" value="${val ?? 0}">
        ${isSeed ? `<button class="dice" data-dice="${esc(f.name)}" title="${t("create.dice.tip")}">🎲</button>` : ""}</div></div>`;
    } else {
      const long = typeof val === "string" && (val.length > 60 || /text|prompt|caption|negative/i.test(f.name));
      html += `<div class="field">${label}${long
        ? `<textarea class="input" rows="5" data-f="${esc(f.name)}">${esc(val ?? "")}</textarea>`
        : `<input class="input" data-f="${esc(f.name)}" value="${esc(val ?? "")}">`}</div>`;
    }
  }
  if (!scalars.length) html += `<div class="muted">${t("ed.insp.none")}</div>`;
  html += `<div style="margin-top:14px" class="row">
    <button class="btn sm danger ghost" id="insp-del">${t("ed.delnode")}</button></div>`;
  body.innerHTML = html;
  body.querySelectorAll("[data-f]").forEach((el) => {
    el.addEventListener("change", () => {
      const name = el.dataset.f;
      let v = el.value;
      const f = scalars.find((x) => x.name === name);
      if (f && (f.type === "INT")) v = parseInt(v) || 0;
      else if (f && (f.type === "FLOAT" || f.type === "NUMBER")) v = parseFloat(v) || 0;
      else if (f && f.type === "BOOLEAN") v = v === "true";
      cur.api[selected].inputs[name] = v;
      toast(t("ed.changed") + name, "");
    });
  });
  body.querySelectorAll("[data-dice]").forEach((b) => b.addEventListener("click", () => {
    const name = b.dataset.dice;
    cur.api[selected].inputs[name] = Math.floor(Math.random() * 2 ** 31);
    renderInspector();
  }));
  body.querySelector("#insp-del").addEventListener("click", () => delNode(selected));
}

/* ================= 节点面板 ================= */
async function openPalette(x, y) {
  if (!objectInfo) {
    toast(t("ed.catalog.pull"));
    const r = await api("/api/object_info");
    if (!r.ok) { toast(r.error || t("ed.needonline"), "err"); return; }
    objectInfo = r.object_info;
  }
  const pal = $("#node-palette");
  pal.hidden = false;
  pal.style.left = Math.min(x, innerWidth - 320) + "px";
  pal.style.top = Math.min(y, innerHeight - 440) + "px";
  $("#palette-search").value = "";
  renderPalette();
  $("#palette-search").focus();
}

function renderPalette() {
  const q = $("#palette-search").value.trim().toLowerCase();
  const box = $("#palette-list");
  box.innerHTML = "";
  const groups = new Map();
  for (const name of Object.keys(objectInfo)) {
    if (q && !name.toLowerCase().includes(q)) continue;
    const cat = name.includes("/") ? name.split("/")[0] : t("ed.common");
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat).push(name);
  }
  const common = t("ed.common");
  const entries = [...groups.entries()].sort((a, b) => (a[0] === common ? -1 : b[0] === common ? 1 : a[0].localeCompare(b[0])));
  let shown = 0;
  for (const [cat, names] of entries) {
    if (shown > 300) break;
    const h = document.createElement("div");
    h.className = "pal-group"; h.textContent = `${cat} (${names.length})`;
    box.appendChild(h);
    for (const n of names.slice(0, q ? 40 : 12)) {
      shown++;
      const it = document.createElement("div");
      it.className = "pal-item"; it.textContent = n.split("/").pop();
      it.title = n;
      it.addEventListener("click", () => { addNode(n); $("#node-palette").hidden = true; });
      box.appendChild(it);
    }
  }
  if (!shown) box.innerHTML = `<div class="muted pad">${t("ed.search.none")}</div>`;
}

function addNode(classType) {
  const id = nextId();
  const s = schemaOf(classType);
  const inputs = {};
  if (s) {
    for (const [name, def] of Object.entries(s.input?.required || {})) {
      const t = Array.isArray(def) ? def[0] : "?";
      if (typeof t === "string" && /^[A-Z][A-Z_]*$/.test(t)) continue;
      if (Array.isArray(t)) inputs[name] = t[0] ?? "";
      else if (t === "INT" || t === "FLOAT") inputs[name] = def?.[1]?.default ?? 0;
      else if (t === "BOOLEAN") inputs[name] = def?.[1]?.default ?? false;
      else if (/seed/i.test(name)) inputs[name] = Math.floor(Math.random() * 2 ** 31);
      else inputs[name] = def?.[1]?.default ?? "";
    }
  }
  // 放到视图中心
  const r = svg.getBoundingClientRect();
  const c = { x: (r.width / 2 - view.x) / view.k, y: (r.height / 2 - view.y) / view.k };
  const off = (Object.keys(cur.api).length % 5) * 24;
  cur.api[id] = { class_type: classType, inputs };
  cur.layout[id] = [c.x - NODE_W / 2 + off, c.y - 40 + off];
  renderGraph();
  selectNode(id);
}

function onCanvasDblClick(e) {
  if (e.target.closest(".node-g")) return;
  openPalette(e.clientX - 150, e.clientY - 40);
}

/* ================= 保存/运行/导入导出 ================= */
async function saveWorkflow() {
  const name = $("#wf-name").value.trim() || t("ed.untitled");
  let id = cur.id;
  if (cur.builtin || !id) id = "wf" + Date.now().toString(36);
  const r = await api("/api/workflows", {
    method: "POST",
    body: { id, name, api: cur.api, layout: cur.layout, builtin_copy: cur.builtin, created: cur.created },
  });
  if (r.ok) {
    toast(tf("ed.saved", name), "ok");
    cur = r.workflow; cur.builtin = false;
    await loadList();
    renderListSel();
  } else toast(r.error, "err");
}

async function runWorkflow() {
  if (!Object.keys(cur.api).length) { toast(t("err.empty.workflow"), "err"); return; }
  const times = prompt(t("ed.run.times"), "1");
  if (times === null) return;
  const r = await api("/api/prompt", {
    method: "POST",
    body: { name: cur.name, prompt: cur.api, times: Math.max(1, parseInt(times) || 1) },
  });
  r.ok ? (toast(r.msg, "ok"), goto("runs")) : toast(r.msg || r.error, "err");
}

async function onImportFiles(e) {
  const files = [...e.target.files];
  e.target.value = "";
  for (const f of files) {
    try {
      if (f.name.toLowerCase().endsWith(".png")) {
        const txt = await pngTextChunks(f);
        const ui = txt.workflow ? JSON.parse(txt.workflow) : null;
        const ap = txt.prompt ? JSON.parse(txt.prompt) : null;
        if (ap) { loadImported(ap, f.name); continue; }
        if (ui) { await importUI(ui, f.name); continue; }
        toast(tf("ed.noembed.f", f.name), "err");
      } else {
        const data = JSON.parse(await f.text());
        if (data.nodes) await importUI(data, f.name);
        else if (typeof data === "object") loadImported(data, f.name);
        else toast(t("ed.badjson"), "err");
      }
    } catch (err) { toast(tf("ed.import.fail.f", f.name, err.message), "err"); }
  }
}

async function importUI(ui, filename) {
  toast(t("ed.converting"));
  const r = await api("/api/convert", { method: "POST", body: { ui } });
  if (!r.ok) { toast(r.error, "err"); return; }
  loadImported(r.api, filename);
  if (r.warnings?.length) toast(t("ed.import.warn") + "\n" + r.warnings.join("\n"), "err");
  // 顺便用 UI 坐标
  if (ui.nodes) for (const n of ui.nodes) cur.layout[String(n.id)] = [n.pos?.[0] || 0, n.pos?.[1] || 0];
  renderGraph(); fitView();
}

function loadImported(apiGraph, filename) {
  cur = { id: null, name: t("ed.prefix") + filename.replace(/\.[^.]+$/, "").slice(0, 40), api: apiGraph, layout: {}, builtin: false };
  afterLoad();
  toast(tf("ed.imported.n", Object.keys(apiGraph).length), "ok");
}

function exportApi() {
  const blob = new Blob([JSON.stringify(cur.api, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (cur.name || "workflow") + ".api.json";
  a.click();
}

/* 浏览器端解析 PNG tEXt 块（导入 PNG 工作流用） */
async function pngTextChunks(file) {
  const buf = await file.arrayBuffer();
  const dv = new DataView(buf);
  const dec = new TextDecoder("utf-8");
  const out = {};
  let pos = 8;
  while (pos + 12 <= buf.byteLength) {
    const len = dv.getUint32(pos);
    const type = String.fromCharCode(dv.getUint8(pos + 4), dv.getUint8(pos + 5), dv.getUint8(pos + 6), dv.getUint8(pos + 7));
    if (type === "tEXt") {
      const bytes = new Uint8Array(buf, pos + 8, len);
      const z = bytes.indexOf(0);
      if (z > 0) {
        const kw = dec.decode(bytes.slice(0, z));
        if (kw === "prompt" || kw === "workflow") out[kw] = dec.decode(bytes.slice(z + 1));
      }
    }
    if (type === "IDAT") break;
    pos += 12 + len;
  }
  return out;
}
