/* app.js — 核心：API 封装、路由、SSE、Toast、全局状态 */
import { initGallery, galleryRefresh, openLightboxPublic } from "./gallery.js";
import { initEditor } from "./editor.js";
import { initRuns, runsOnSSE } from "./runs.js";
import { initMisc } from "./misc.js";
import { initCreate, refreshFeed } from "./create.js";
import { initLauncher } from "./launcher.js";
import { initPipeline } from "./pipeline.js";
import { initTemplates } from "./templates.js";
import { applyI18n } from "./i18n.js";

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
const views = ["create", "gallery", "editor", "templates", "runs", "pipeline", "launcher", "obsidian", "agent", "settings"];
export function goto(view) {
  if (!views.includes(view)) return;
  location.hash = "#" + view;
}
function applyHash() {
  let v = (location.hash || "#create").slice(1);
  if (!views.includes(v)) v = "create";
  $$(".view").forEach((el) => el.classList.toggle("active", el.id === "view-" + v));
  $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === v));
  if (v === "gallery") galleryRefresh(false);
  else {
    const bb = $("#batch-bar");
    if (bb && !bb.hidden && v !== "gallery") bb.hidden = true; // 批量操作只在画廊生效
  }
  if (v === "create") refreshFeed();
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
    if (t === "watchdog") {
      const phase = d.phase;
      if (phase === "down") toast("看门狗：ComfyUI 掉线，准备自动重启…", "err");
      if (phase === "restart") toast(d.ok ? "看门狗：已重启 ComfyUI" : "看门狗：重启失败 " + (d.msg || ""), d.ok ? "ok" : "err");
      if (phase === "resumed") toast(`看门狗：已自动续跑 ${d.count} 个中断任务`, "ok");
    }
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
let offlineToasted = false;
export function setComfyDot(on) {
  if (on === comfyOnline) return;
  comfyOnline = on;
  $("#comfy-dot").className = "dot " + (on ? "on" : "off");
  $("#comfy-dot-text").textContent = on ? "ComfyUI 在线" : "ComfyUI 离线";
  if (!on && !offlineToasted) { toast("ComfyUI 掉线，自动重连中…（生成任务会排队等它回来）", "err"); offlineToasted = true; }
  if (on) offlineToasted = false;
}

/* ---------- 硬件状态条（2s 轮询） ---------- */
const fmtGB = (b) => (b / 1073741824).toFixed(1) + "G";
function hwLoop() {
  const upd = async () => {
    try {
      const h = await (await fetch("/api/hardware")).json();
      if (!h.ok) return;
      const g = h.gpu;
      $("#hw-gpu-name").textContent = g?.name || "GPU";
      if (g?.vram_total) {
        const used = g.vram_used != null ? g.vram_used : (g.vram_total - (g.vram_free || 0));
        $("#hw-vram-fill").style.width = Math.min(100, used / g.vram_total * 100) + "%";
        $("#hw-vram-text").textContent = fmtGB(used) + " / " + fmtGB(g.vram_total);
      } else {
        $("#hw-vram-text").textContent = "—";
      }
      $("#hw-util-text").textContent = g?.util != null ? Math.round(g.util) + "%" : "—";
      const t = $("#hw-temp-text");
      t.textContent = g?.temp != null ? Math.round(g.temp) + "°C" : "—";
      t.classList.toggle("hot", g?.temp != null && g.temp >= 83);
      if (h.ram?.total) {
        const used = h.ram.total - (h.ram.free || 0);
        $("#hw-ram-fill").style.width = Math.min(100, used / h.ram.total * 100) + "%";
        $("#hw-ram-text").textContent = fmtGB(used) + " / " + fmtGB(h.ram.total);
      } else {
        $("#hw-ram-text").textContent = "—";
      }
      $("#hw-queue-text").textContent = h.queue ?? 0;
    } catch { /* 服务未就绪时静默 */ }
  };
  upd();
  setInterval(upd, 2000);
}

window.APP_VERSION = "ComfyAgent v3.0.0";

/* ---------- 全局快捷键 ---------- */
const VIEW_KEYS = { "1": "create", "2": "gallery", "3": "editor", "4": "runs", "5": "pipeline", "6": "launcher", "7": "obsidian", "8": "agent" };
document.addEventListener("keydown", (e) => {
  if (isTypingTarget(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
  if (VIEW_KEYS[e.key]) goto(VIEW_KEYS[e.key]);
  if (e.key === "/") {
    e.preventDefault();
    goto("gallery");
    setTimeout(() => $("#g-search")?.focus(), 80);
  }
});
const isTypingTarget = (t) => ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);

/* ---------- 命令面板 Ctrl+K ---------- */
let cmdkItems = [];
function initCmdk() {
  const box = $("#cmdk"), input = $("#cmdk-input"), list = $("#cmdk-list");
  const open = async () => {
    box.hidden = false; input.value = ""; renderCmdk("");
    input.focus();
  };
  const close = () => { box.hidden = true; };
  const buildItems = async () => {
    const items = [];
    const labels = { create: "去创作", gallery: "去画廊", editor: "去工作流", runs: "去任务", obsidian: "去知识库", agent: "去助手", settings: "去设置" };
    for (const v of views) items.push({ label: labels[v], key: "页面", run: () => goto(v) });
    try {
      const r = await api("/api/workflows");
      for (const wf of (r.workflows || [])) items.push({
        label: `运行「${wf.name}」`, key: "工作流",
        run: async () => {
          const rr = await api("/api/prompt", { method: "POST", body: { name: wf.name, prompt: wf.api, times: 1 } });
          toast(rr.msg || rr.error, rr.ok ? "ok" : "err");
          if (rr.ok) goto("runs");
        },
      });
    } catch { }
    items.push({ label: "⏹ 中断当前任务", key: "动作", run: async () => { await api("/api/interrupt", { method: "POST", body: {} }); toast("已发送中断", "ok"); } });
    items.push({ label: "🧹 清空队列", key: "动作", run: async () => { await api("/api/clear_queue", { method: "POST", body: {} }); toast("队列已清空", "ok"); } });
    return items;
  };
  const renderCmdk = (q) => {
    q = q.trim().toLowerCase();
    list.innerHTML = "";
    cmdkItems.filter((i) => !q || i.label.toLowerCase().includes(q)).slice(0, 12).forEach((i, idx) => {
      const el = document.createElement("div");
      el.className = "cmdk-item" + (idx === 0 ? " hot" : "");
      el.innerHTML = `<span>${i.label}</span><span class="k">${i.key}</span>`;
      el.addEventListener("click", () => { close(); i.run(); });
      list.appendChild(el);
    });
  };
  document.addEventListener("keydown", async (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (box.hidden) { open(); cmdkItems = await buildItems(); renderCmdk(input.value); }
      else close();
    }
    if (e.key === "Escape" && !box.hidden) close();
  });
  input.addEventListener("input", () => renderCmdk(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const first = list.querySelector(".cmdk-item");
      if (first) { close(); first.click(); }
    }
  });
  box.addEventListener("click", (e) => { if (e.target.id === "cmdk") close(); });
}

/* ---------- 启动 ---------- */
window.addEventListener("error", (e) => {
  if (!window.__bootError) window.__bootError = (e.message || "") + " @" + (e.filename || "") + ":" + (e.lineno || "");
});
/* ---------- 服务重启自愈：后端未就绪时显示等待页并自动恢复 ---------- */
async function waitServerAndBoot() {
  try {
    await fetch("/api/status", { cache: "no-store" });
  } catch {
    document.body.innerHTML = `<div style="position:fixed;inset:0;background:#08090d;color:#a8aec2;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:system-ui,sans-serif;gap:14px;z-index:999">
      <div style="font-size:40px">⏳</div>
      <div style="font-size:15px;color:#f0f2f8">ComfyAgent 服务正在重启…</div>
      <div style="font-size:12px">页面将自动恢复（每 2 秒探测一次）</div></div>`;
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      try { await fetch("/api/status", { cache: "no-store" }); break; } catch { }
    }
    location.reload();
    return;
  }
  boot();
}
async function boot() {
  try {
    applyI18n();
    initCreate();
    initGallery();
    initEditor();
    initTemplates();
    initRuns();
    initLauncher();
    initPipeline();
    initMisc();
    applyHash();
    connectSSE();
    hwLoop();
    initCmdk();
    $("#nav-about")?.addEventListener("click", () => { $("#about-modal").hidden = false; });
    const st = await api("/api/status");
    setComfyDot(st.comfy_online);
  } catch (err) {
    window.__bootError = (err && err.stack) || String(err);
    console.error("[ComfyAgent] boot failed:", err);
    const box = $("#app");
    if (box) {
      const el = document.createElement("div");
      el.style.cssText = "position:fixed;top:60px;left:212px;z-index:300;max-width:520px;background:#2a1418;border:1px solid var(--err);border-radius:12px;padding:14px 16px;font-size:12px;color:#ffd9df;white-space:pre-wrap";
      el.textContent = "界面初始化出错：" + ((err && err.message) || err) + "（刷新重试；若反复出现，删除 data/ 后重启）";
      document.body.appendChild(el);
    }
  }
}
waitServerAndBoot();
