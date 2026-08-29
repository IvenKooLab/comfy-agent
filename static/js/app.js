/* app.js — 核心：API 封装、路由、SSE、Toast、全局状态 */
import { initGallery, galleryRefresh } from "./gallery.js";
import { initEditor } from "./editor.js";
import { initRuns, runsOnSSE } from "./runs.js";
import { initMisc } from "./misc.js";

export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => [...document.querySelectorAll(sel)];

export async function api(path, opts = {}) {
  const r = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({ ok: false, error: "响应解析失败" }));
  if (!r.ok && !data.error) data.error = `HTTP ${r.status}`;
  return data;
}

export function toast(msg, type = "") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

export function fmtSize(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + u[i];
}
export function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const pad = (x) => String(x).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.toDateString() === now.toDateString()) return `今天 ${hm}`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}
export function mediaUrl(path, extra = {}) {
  const q = new URLSearchParams({ path, ...extra });
  return "/api/media?" + q.toString();
}

/* ---------- 路由 ---------- */
const views = ["gallery", "editor", "runs", "obsidian", "agent", "settings"];
export function goto(view) {
  if (!views.includes(view)) return;
  location.hash = "#" + view;
}
function applyHash() {
  let v = (location.hash || "#gallery").slice(1);
  if (!views.includes(v)) v = "gallery";
  $$(".view").forEach((el) => el.classList.toggle("active", el.id === "view-" + v));
  $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === v));
  if (v === "gallery") galleryRefresh(false);
}
window.addEventListener("hashchange", applyHash);

/* ---------- SSE 实时事件 ---------- */
let es = null;
function connectSSE() {
  es = new EventSource("/api/events");
  es.onmessage = (e) => {
    let ev = {};
    try { ev = JSON.parse(e.data); } catch { return; }
    const t = ev.type, d = ev.data || {};
    if (t === "comfy_status") setComfyDot(!!d.online);
    if (t === "execution_success" || t === "execution_error" || t === "execution_cached") {
      setTimeout(() => galleryRefresh(true), 1500);
    }
    if (t === "execution_error") toast("有任务执行失败，到「任务」页查看", "err");
    runsOnSSE(ev);
    document.dispatchEvent(new CustomEvent("sse", { detail: ev }));
  };
  es.onerror = () => { /* EventSource 会自动重连 */ };
}

let comfyOnline = null;
export function setComfyDot(on) {
  if (on === comfyOnline) return;
  comfyOnline = on;
  $("#comfy-dot").className = "dot " + (on ? "on" : "off");
  $("#comfy-dot-text").textContent = on ? "ComfyUI 在线" : "ComfyUI 离线";
}

/* ---------- 启动 ---------- */
async function boot() {
  initGallery();
  initEditor();
  initRuns();
  initMisc();
  applyHash();
  connectSSE();
  try {
    const st = await api("/api/status");
    setComfyDot(st.comfy_online);
  } catch { setComfyDot(false); }
}
boot();
