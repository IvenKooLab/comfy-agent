/* misc.js — Obsidian 知识库页 + 智能助手页 + 设置页 + 语言/更新 */
import { $, $$, api, toast, goto } from "./app.js";
import { getLang, setLang, t, tf } from "./i18n.js";

export function initMisc() {
  initObsidian();
  initAgent();
  initSettings();
  initWizard();
  initAbout();
}

function initAbout() {
  $("#about-version").textContent = (window.APP_VERSION || "") + t("about.tag");
  $("#about-close").addEventListener("click", () => { $("#about-modal").hidden = true; });
  $("#about-modal").addEventListener("click", (e) => { if (e.target.id === "about-modal") e.target.hidden = true; });
}

/* ================= 首次运行向导 ================= */
function initWizard() {
  if (localStorage.getItem("comfyagent_wizard")) return;
  $("#wizard").hidden = false;
  api("/api/settings").then((r) => {
    if (!r.ok) return;
    $("#w2-input").value = r.settings.output_dir || "";
    $("#w3-input").value = r.settings.vault_path || "";
  });
  $("#w1-btn").addEventListener("click", async () => {
    $("#w1-state").textContent = t("wd.detecting");
    const st = await api("/api/status");
    if (st.comfy_online) {
      $("#w1-state").innerHTML = tf("wizard.conn", (st.system_stats?.system || {}).comfyui_version || "?");
      $("#w1").classList.add("done");
    } else {
      $("#w1-state").textContent = t("wd.notdetected");
    }
  });
  $("#wizard-skip").addEventListener("click", () => {
    localStorage.setItem("comfyagent_wizard", "1");
    $("#wizard").hidden = true;
  });
  $("#wizard-done").addEventListener("click", async () => {
    const body = {};
    if ($("#w2-input").value.trim()) body.output_dir = $("#w2-input").value.trim();
    if ($("#w3-input").value.trim()) body.vault_path = $("#w3-input").value.trim();
    if ($("#w4-input").value.trim()) body.llm_key = $("#w4-input").value.trim();
    if (Object.keys(body).length) await api("/api/settings", { method: "POST", body });
    localStorage.setItem("comfyagent_wizard", "1");
    $("#wizard").hidden = true;
    toast(t("wizard.saved"), "ok");
  });
}

/* ================= Obsidian ================= */
let vaultBase = "";
let vaultNotes = [];

function initObsidian() {
  $("#obs-sync").addEventListener("click", async () => {
    const r = await api("/api/obsidian/sync", { method: "POST", body: {} });
    r.ok ? toast(tf("obsidian.synced", r.count, r.dir), "ok") : toast(r.error, "err");
    refreshObsidian();
  });
  $("#obs-refresh").addEventListener("click", refreshObsidian);
  $("#obs-search").addEventListener("input", renderNoteList);
  $("#obs-preview-close").addEventListener("click", () => { $("#obs-preview").hidden = true; });
  // 切到该页时刷新
  new MutationObserver(() => {
    if ($("#view-obsidian").classList.contains("active")) refreshObsidian();
  }).observe($("#view-obsidian"), { attributes: true, attributeFilter: ["class"] });
  refreshObsidian();
}

async function refreshObsidian() {
  const st = await api("/api/obsidian/status");
  if (!st.ok) return;
  vaultBase = st.path;
  $("#obs-status").innerHTML = `
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-size:15px;font-weight:700">${st.valid ? t("obs.conn") : t("obs.bad")}</div>
        <div class="muted">${esc(st.path)} ${st.is_vault ? t("obs.vault.ok") : t("obs.vault.no")}</div>
      </div>
      <div class="muted">${tf("obs.attach", st.attachments)}</div>
    </div>
    <div class="muted margin-top">${t("obs.dirs")}</div>`;
  loadVault();
  const arch = await api("/api/obsidian/archives");
  const ab = $("#obs-archives");
  ab.innerHTML = arch.ok && arch.archives.length
    ? arch.archives.map((a) => `<div class="obs-row">
        <span>${esc(a.title)}</span><span class="muted">${a.count}${t("unit.count")} ${esc(a.time)}</span>
        <a class="obs-uri grow" href="${a.uri}">${t("obs.open")}</a></div>`).join("")
    : `<div class="obs-row muted">${t("empty.archives")}</div>`;
}

/* —— 全库可视化：统计 + 搜索列表 + 双链图 —— */
async function loadVault() {
  const r = await api("/api/obsidian/vault");
  if (!r.ok) return;
  vaultNotes = r.notes;
  const s = r.stats;
  $("#obs-stats").innerHTML = [
    [t("kb.stat.notes"), s.count], [t("kb.stat.words"), s.words >= 10000 ? (getLang() === "en" ? Math.round(s.words / 1000) + "k" : (s.words / 10000).toFixed(1) + "w") : s.words],
    [t("kb.stat.links"), s.links], [t("kb.stat.recent"), "+" + s.recent7],
  ].map(([l, n]) => `<div class="obs-stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
  renderNoteList();
  drawGraph();
}

function renderNoteList() {
  const q = ($("#obs-search").value || "").trim().toLowerCase();
  const list = vaultNotes.filter((n) => !q || n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q));
  $("#obs-notelist").innerHTML = list.length
    ? list.map((n) => `<div class="note-item" data-p="${n.path}"><span class="nm">📄 ${n.name}</span><span class="meta">${n.words}${t("unit.words")}</span></div>`).join("")
    : `<div class="muted">${t("kb.search.none")}</div>`;
  $$("#obs-notelist .note-item").forEach((el) => el.addEventListener("click", () => openNotePreview(el.dataset.p)));
}

async function openNotePreview(p) {
  const r = await api("/api/obsidian/note?path=" + encodeURIComponent(p));
  if (!r.ok) { toast(r.error, "err"); return; }
  $("#obs-preview").hidden = false;
  $("#obs-preview-title").textContent = p;
  $("#obs-preview-content").textContent = r.content;
  const q = encodeURIComponent;
  const vname = vaultBase.split(/[\\/]/).filter(Boolean).pop() || "vault";
  $("#obs-preview-open").href = `obsidian://open?vault=${q(vname)}&file=${q(p.replace(/\.md$/, ""))}`;
  $("#obs-preview").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* 力导向双链关系图（原生 canvas，零依赖） */
function drawGraph() {
  const canvas = $("#obs-graph");
  if (!canvas) return;
  const W = canvas.clientWidth || 640, H = 430;
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  const nodes = vaultNotes.map((n, i) => ({
    id: n.path, label: n.name, words: n.words,
    x: W / 2 + Math.cos((i / Math.max(vaultNotes.length, 1)) * 6.283) * W * 0.32,
    y: H / 2 + Math.sin((i / Math.max(vaultNotes.length, 1)) * 6.283) * H * 0.32,
    vx: 0, vy: 0,
  }));
  const byLabel = new Map(nodes.map((n) => [n.label.toLowerCase(), n]));
  const seen = new Set(), E = [];
  for (const n of vaultNotes)
    for (const l of n.links) {
      const s = nodes.find((x) => x.path === n.path);
      const t = byLabel.get(l.trim().toLowerCase());
      if (!s || !t || s === t) continue;
      const k = [s.id, t.id].sort().join("|");
      if (!seen.has(k)) { seen.add(k); E.push([s, t]); }
    }
  const graphToken = canvas.dataset.graphToken = String(Math.random());
  let alpha = 1, drag = null;
  function tick() {
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        const d2 = dx * dx + dy * dy || 1, d = Math.sqrt(d2), rep = 3200 / d2;
        dx /= d; dy /= d;
        a.vx -= dx * rep; a.vy -= dy * rep; b.vx += dx * rep; b.vy += dy * rep;
      }
    for (const [a, b] of E) {
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1, k = (d - 150) * 0.03;
      dx /= d; dy /= d;
      a.vx += dx * k; a.vy += dy * k; b.vx -= dx * k; b.vy -= dy * k;
    }
    for (const n of nodes) {
      n.vx += (W / 2 - n.x) * 0.005; n.vy += (H / 2 - n.y) * 0.005;
      n.x += n.vx * alpha; n.y += n.vy * alpha;
      n.vx *= 0.85; n.vy *= 0.85;
      n.x = Math.max(46, Math.min(W - 46, n.x)); n.y = Math.max(26, Math.min(H - 26, n.y));
    }
    alpha *= 0.996;
  }
  canvas.onmousedown = (e) => {
    const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    drag = nodes.find((n) => (n.x - x) ** 2 + (n.y - y) ** 2 < 420) || null;
  };
  canvas.onmousemove = (e) => {
    if (!drag) return;
    const r = canvas.getBoundingClientRect();
    drag.x = e.clientX - r.left; drag.y = e.clientY - r.top;
    alpha = Math.max(alpha, 0.3);
  };
  canvas.onmouseup = () => { drag = null; };
  canvas.ondblclick = (e) => {
    const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const n = nodes.find((n) => (n.x - x) ** 2 + (n.y - y) ** 2 < 420);
    if (n) openNotePreview(n.path);
  };
  (function frame() {
    if (canvas.dataset.graphToken !== graphToken) return; // 旧循环自动退出
    if (alpha > 0.004 || drag) tick();
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(139,92,246,.35)"; ctx.lineWidth = 1.2;
    for (const [a, b] of E) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
    for (const n of nodes) {
      const r = Math.max(6, Math.min(16, 4 + Math.sqrt(n.words) / 14));
      const g = ctx.createRadialGradient(n.x - 2, n.y - 2, 1, n.x, n.y, r);
      g.addColorStop(0, "#a78bfa"); g.addColorStop(1, "#6d28d9");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 6.283); ctx.fill();
      ctx.fillStyle = "#a8aec2"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(n.label, n.x, n.y + r + 12);
    }
    requestAnimationFrame(frame);
  })();
}

/* ================= Agent ================= */
const CHAT_KEY = "comfyagent_chat";

function loadChatHistory() { try { return JSON.parse(localStorage.getItem(CHAT_KEY) || "[]"); } catch { return []; } }
function saveChatHistory(log) {
  try {
    const items = [...log.querySelectorAll(".msg")]
      .filter((m) => !m.classList.contains("time") && !m.querySelector(".typing"))
      .slice(-40)
      .map((m) => ({ who: m.classList.contains("user") ? "user" : "bot", text: m.innerText }));
    localStorage.setItem(CHAT_KEY, JSON.stringify(items));
  } catch { }
}

function initAgent() {
  const log = $("#chat-log");
  const say = (text, who = "bot", actions = null, silent = false) => {
    const el = document.createElement("div");
    el.className = `msg ${who}`;
    el.textContent = text;
    if (actions?.length && who === "bot") {
      const box = document.createElement("div");
      box.className = "msg-actions";
      for (const a of actions) {
        if (a.type === "submitted") {
          const b = document.createElement("button");
          b.className = "btn sm"; b.textContent = t("kb.viewjobs");
          b.addEventListener("click", () => goto("runs"));
          box.appendChild(b);
        }
        if (a.type === "archive" && a.uri) {
          const aa = document.createElement("a");
          aa.className = "btn sm"; aa.textContent = t("kb.opennote"); aa.href = a.uri;
          box.appendChild(aa);
        }
        if (a.type === "open") {
          const b = document.createElement("button");
          b.className = "btn sm"; b.textContent = t("kb.goto");
          b.addEventListener("click", () => goto(a.view));
          box.appendChild(b);
        }
      }
      el.appendChild(box);
    }
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    if (!silent) saveChatHistory(log);
    return el;
  };
  // 恢复历史
  const isGreeting = (txt) => typeof txt === "string" &&
    (txt.startsWith("你好，我是创作台助手") || txt.startsWith("Hi, I'm your console assistant"));
  const hist = loadChatHistory().filter((m) => !isGreeting(m.text));
  if (hist.length) {
    for (const m of hist) say(m.text, m.who, null, true);
  } else {
    say(t("agent.hello"), "bot");
  }

  const send = async () => {
    const text = $("#chat-input").value.trim();
    if (!text) return;
    $("#chat-input").value = "";
    say(text, "user");
    const holder = document.createElement("div");
    holder.className = "msg bot";
    holder.innerHTML = `<span class="typing"><i></i><i></i><i></i></span>`;
    log.appendChild(holder); log.scrollTop = log.scrollHeight;
    const r = await api("/api/agent", { method: "POST", body: { text } });
    holder.remove();
    say(r.ok ? r.reply : (r.error || t("agent.error")), "bot", r.actions);
  };
  $("#chat-send").addEventListener("click", send);
  $("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  $$(".chat-quick .chip").forEach((c) => c.addEventListener("click", () => {
    $("#chat-input").value = c.dataset.q; send();
  }));
}

/* ================= 设置 ================= */
let llmPresets = [];

function initLLMSettings() {
  api("/api/llm/providers").then((r) => {
    if (!r.ok) return;
    llmPresets = r.presets;
    const sel = $("#s-llm-provider");
    const fillVendors = () => { sel.innerHTML = llmPresets.map((p) => `<option value="${p.id}">${vendorLabel(p)}</option>`).join(""); sel.value = sel.value || "zhipu"; };
    fillVendors();
    window.addEventListener("langchange", fillVendors);
    api("/api/settings").then((s) => {
      if (!s.ok) return;
      sel.value = s.settings.llm_provider || "zhipu";
      onProviderChange(s.settings.llm_model);
    });
  });
  $("#s-llm-provider").addEventListener("change", () => onProviderChange());
  $("#s-llm-refresh").addEventListener("click", () => refreshLLMModels());
}

/* 厂商标签英文映射（服务端 name 为中文） */
const VENDOR_EN = {
  zhipu: "Zhipu GLM", deepseek: "DeepSeek", moonshot: "Moonshot Kimi", dashscope: "Alibaba Qwen",
  siliconflow: "SiliconFlow", openai: "OpenAI", custom: "Custom (OpenAI-compatible)",
};
const vendorLabel = (p) => (getLang() === "en" && VENDOR_EN[p.id]) ? VENDOR_EN[p.id] : p.name;

function currentPreset() {
  return llmPresets.find((p) => p.id === $("#s-llm-provider").value) || { base: "", models: [] };
}

function onProviderChange(keepModel) {
  const p = currentPreset();
  if (p.id !== "custom" && p.base) $("#s-llm-base").value = p.base;
  // 预设兜底模型列表先填上，再尝试动态拉取
  fillModelSelect(p.models || []);
  if (keepModel) $("#s-llm-model").value = keepModel;
  refreshLLMModels(keepModel);
}

function fillModelSelect(models, keep) {
  const sel = $("#s-llm-model");
  const cur = keep || sel.value;
  sel.innerHTML = (models.length ? models : [""]).map((m) => `<option>${m}</option>`).join("");
  if (cur && models.includes(cur)) sel.value = cur;
}

async function refreshLLMModels(keep) {
  const manual = $("#s-llm-model-manual");
  const btn = $("#s-llm-refresh");
  btn.disabled = true; btn.textContent = t("st.pulling");
  try {
    const body = { provider: $("#s-llm-provider").value, base_url: $("#s-llm-base").value.trim() };
    const key = $("#s-llm-key").value.trim();
    if (key) body.key = key;
    const r = await api("/api/llm/models", { method: "POST", body });
    if (r.ok && r.models.length) {
      fillModelSelect(r.models, keep || r.models.includes($("#s-llm-model").value) ? $("#s-llm-model").value : undefined);
      manual.style.display = "none";
      toast(tf("toast.models.fetched", r.models.length), "ok");
    } else {
      manual.style.display = "block";
      toast(t("toast.model.fetch.fail"), "err");
    }
  } finally {
    btn.disabled = false; btn.textContent = t("settings.llm.pull");
  }
}

function initSettings() {
  initLLMSettings();
  loadForm();
  $("#s-backup").addEventListener("click", async () => {
    const r = await api("/api/backup", { method: "POST", body: { reason: "manual" } });
    $("#s-backup-info").textContent = r.ok ? tf("backup.done", r.file) : (r.error || t("act.fail"));
    toast(r.ok ? t("toast.saved") : t("toast.save.fail"), r.ok ? "ok" : "err");
  });
  $("#s-lang").addEventListener("change", (e) => setLang(e.target.value));
  $("#s-update").addEventListener("click", async () => {
    const info = $("#s-update-info");
    info.hidden = false;
    info.textContent = t("st.checking");
    const r = await api("/api/update/check");
    if (!r.ok) { info.textContent = r.error; return; }
    if (r.newer) {
      info.innerHTML = tf("upd.found", r.latest, r.local) + ` <a href="${r.url}" target="_blank">${t("upd.openrel")}</a>`;
    } else {
      info.textContent = r.latest ? tf("upd.latest", r.local, r.latest) : tf("upd.latest.only", r.local);
    }
  });
  $("#s-openrel").addEventListener("click", async () => {
    const r = await api("/api/settings");
    const repo = r.ok ? r.settings.gitee_repo : "";
    window.open(`https://gitee.com/${repo || "gu-dongwei/comfy-agent"}/releases`, "_blank");
  });
  $("#s-save").addEventListener("click", async () => {
    const body = {
      comfy_url: $("#s-comfy").value.trim(),
      output_dir: $("#s-output").value.trim(),
      vault_path: $("#s-vault").value.trim(),
      port: parseInt($("#s-port").value) || 8190,
      llm_provider: $("#s-llm-provider").value,
      llm_base_url: $("#s-llm-base").value.trim(),
      llm_model: ($("#s-llm-model-manual").style.display !== "none" && $("#s-llm-model-manual").value.trim())
        || $("#s-llm-model").value,
      comfy_watchdog: $("#s-watchdog").checked,
      comfy_autorequeue: $("#s-autorequeue").checked,
      lan_access: $("#s-lan").checked,
      batch_auto_retry: parseInt($("#s-batch-retry").value) || 0,
    };
    if ($("#s-llm-key").value.trim()) body.llm_key = $("#s-llm-key").value.trim();
    const r = await api("/api/settings", { method: "POST", body });
    $("#s-msg").textContent = r.ok ? r.msg : r.error;
    toast(r.ok ? t("toast.lang.saved") : r.error, r.ok ? "ok" : "err");
  });
  $("#s-test").addEventListener("click", async () => {
    $("#s-msg").textContent = t("st.testing");
    const st = await api("/api/status");
    const dev = (st.system_stats?.devices || [])[0];
    $("#s-msg").textContent = st.comfy_online
      ? tf("set.test.ok", dev?.name || "?", Math.round((dev?.vram_total || 0) / 1048576))
      : "✗ Offline (is ComfyUI running?)";
  });
}
async function loadForm() {
  const r = await api("/api/settings");
  if (!r.ok) return;
  const s = r.settings;
  $("#s-comfy").value = s.comfy_url || "";
  $("#s-output").value = s.output_dir || "";
  $("#s-vault").value = s.vault_path || "";
  $("#s-port").value = s.port || 8190;
  $("#s-llm-base").value = s.llm_base || s.llm_base_url || "";
  $("#s-llm-key").placeholder = s.has_llm_key ? t("set.key.set") : "sk-…";
  if (s.llm_model) { const m = $("#s-llm-model"); m.innerHTML = `<option>${s.llm_model}</option>`; m.value = s.llm_model; }
  $("#s-watchdog").checked = s.comfy_watchdog !== false;
  $("#s-autorequeue").checked = s.comfy_autorequeue !== false;
  const lan = $("#s-lan"), retry = $("#s-batch-retry");
  if (lan) lan.checked = !!s.lan_access;
  if (retry) retry.value = s.batch_auto_retry != null ? s.batch_auto_retry : 2;
  $("#s-lan").checked = !!s.lan_access;
  $("#s-batch-retry").value = s.batch_auto_retry != null ? s.batch_auto_retry : 2;
  $("#s-lang").value = getLang();
  // 环境卡（迭代27）
  const st = await api("/api/status");
  if (st.ok) {
    const dev = (st.system_stats?.devices || [])[0];
    $("#env-card").innerHTML = `
      <div class="row" style="justify-content:space-between">
        <span>${t("env.ver")}<b>${st.version || "?"}</b></span>
        <span class="muted">ComfyUI ${st.comfy_online ? t("env.online") : t("env.offline")}</span>
      </div>
      <div class="row" style="justify-content:space-between">
        <span class="muted">${st.ffmpeg ? t("env.ffmpeg.ok") : t("env.ffmpeg.none")}</span>
        <span class="muted">${dev ? (dev.name || "") : ""}</span>
      </div>`;
  }
  $("#log-refresh").addEventListener("click", loadLog);
  loadLog();
}
async function loadLog() {
  const r = await api("/api/logs");
  if (r.ok) {
    const pre = $("#log-view");
    pre.textContent = r.lines;
    pre.scrollTop = pre.scrollHeight;
  }
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
