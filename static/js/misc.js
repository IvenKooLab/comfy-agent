/* misc.js — Obsidian 知识库页 + 智能助手页 + 设置页 */
import { $, $$, api, toast, goto } from "./app.js";

export function initMisc() {
  initObsidian();
  initAgent();
  initSettings();
  initWizard();
  initAbout();
}

function initAbout() {
  $("#about-version").textContent = (window.APP_VERSION || "") + " · 本地优先 · 数据不出机器";
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
    $("#w1-state").textContent = "探测中…";
    const st = await api("/api/status");
    if (st.comfy_online) {
      $("#w1-state").innerHTML = `✓ 已连接 ComfyUI（${(st.system_stats?.system || {}).comfyui_version || "?"}）`;
      $("#w1").classList.add("done");
    } else {
      $("#w1-state").textContent = "未检测到 —— 请先启动 ComfyUI，或到设置页修改地址（也可以先跳过，稍后配置）";
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
    if ($("#w4-input").value.trim()) body.zhipu_key = $("#w4-input").value.trim();
    if (Object.keys(body).length) await api("/api/settings", { method: "POST", body });
    localStorage.setItem("comfyagent_wizard", "1");
    $("#wizard").hidden = true;
    toast("设置已保存，开始创作吧 ✦", "ok");
  });
}

/* ================= Obsidian ================= */
function initObsidian() {
  $("#obs-sync").addEventListener("click", async () => {
    const r = await api("/api/obsidian/sync", { method: "POST", body: {} });
    r.ok ? toast(`已同步 ${r.count} 个工作流到 ${r.dir}`, "ok") : toast(r.error, "err");
    refreshObsidian();
  });
  $("#obs-refresh").addEventListener("click", refreshObsidian);
  // 切到该页时刷新
  new MutationObserver(() => {
    if ($("#view-obsidian").classList.contains("active")) refreshObsidian();
  }).observe($("#view-obsidian"), { attributes: true, attributeFilter: ["class"] });
  refreshObsidian();
}

async function refreshObsidian() {
  const st = await api("/api/obsidian/status");
  if (!st.ok) return;
  $("#obs-status").innerHTML = `
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-size:15px;font-weight:700">${st.valid ? "🟢 已连接" : "🔴 库不可用"}</div>
        <div class="muted">${esc(st.path)} ${st.is_vault ? "（检测到 .obsidian，是有效库）" : "（未检测到 .obsidian，请确认路径是库根目录）"}</div>
      </div>
      <div class="muted">笔记 ${st.notes} · 附件 ${st.attachments}</div>
    </div>
    <div class="muted margin-top">归档目录：ComfyAgent/attachments · 笔记：ComfyAgent/notes · 工作流镜像：ComfyAgent/workflows</div>`;

  const arch = await api("/api/obsidian/archives");
  const ab = $("#obs-archives");
  ab.innerHTML = arch.ok && arch.archives.length
    ? arch.archives.map((a) => `<div class="obs-row">
        <span>${esc(a.title)}</span><span class="muted">${a.count} 个文件 · ${esc(a.time)}</span>
        <a class="obs-uri grow" href="${a.uri}">在 Obsidian 中打开 ↗</a></div>`).join("")
    : `<div class="obs-row muted">还没有归档记录。去画廊挑一张图，点「归档」试试。</div>`;

  const notes = await api("/api/obsidian/notes");
  const nb = $("#obs-notes");
  nb.innerHTML = notes.ok && notes.notes.length
    ? notes.notes.map((n) => `<div class="obs-row">
        <span class="grow">${esc(n.file.split("/").pop())}</span>
        <a class="obs-uri" href="${n.uri}">打开 ↗</a></div>`).join("")
    : `<div class="obs-row muted">（暂无笔记）</div>`;
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
          b.className = "btn sm"; b.textContent = "查看任务 →";
          b.addEventListener("click", () => goto("runs"));
          box.appendChild(b);
        }
        if (a.type === "archive" && a.uri) {
          const aa = document.createElement("a");
          aa.className = "btn sm"; aa.textContent = "打开笔记 ↗"; aa.href = a.uri;
          box.appendChild(aa);
        }
        if (a.type === "open") {
          const b = document.createElement("button");
          b.className = "btn sm"; b.textContent = "前往 →";
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
  const hist = loadChatHistory();
  if (hist.length) {
    for (const m of hist) say(m.text, m.who, null, true);
  } else {
    say("你好，我是创作台助手。直接说人话就行：\n· 「画：雪夜竹林里的剑客」\n· 「跑 H3 文生视频 ×2」\n· 「归档最近 10 个」\n· 「状态 / 中断 / 清空队列」", "bot");
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
    say(r.ok ? r.reply : (r.error || "出错了"), "bot", r.actions);
  };
  $("#chat-send").addEventListener("click", send);
  $("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  $$(".chat-quick .chip").forEach((c) => c.addEventListener("click", () => {
    $("#chat-input").value = c.dataset.q; send();
  }));
}

/* ================= 设置 ================= */
function initSettings() {
  loadForm();
  $("#s-save").addEventListener("click", async () => {
    const body = {
      comfy_url: $("#s-comfy").value.trim(),
      output_dir: $("#s-output").value.trim(),
      vault_path: $("#s-vault").value.trim(),
      port: parseInt($("#s-port").value) || 8190,
      zhipu_model: $("#s-zhipu-model").value.trim(),
    };
    if ($("#s-zhipu").value.trim()) body.zhipu_key = $("#s-zhipu").value.trim();
    const r = await api("/api/settings", { method: "POST", body });
    $("#s-msg").textContent = r.ok ? r.msg : r.error;
    toast(r.ok ? "设置已保存" : r.error, r.ok ? "ok" : "err");
  });
  $("#s-test").addEventListener("click", async () => {
    $("#s-msg").textContent = "测试中…";
    const st = await api("/api/status");
    const dev = (st.system_stats?.devices || [])[0];
    $("#s-msg").textContent = st.comfy_online
      ? `✓ 在线 · ${dev?.name || "?"} · 显存 ${Math.round((dev?.vram_total || 0) / 1048576)}MB`
      : "✗ 连不上（ComfyUI 启动了吗？）";
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
  $("#s-zhipu-model").value = s.zhipu_model || "glm-4-flash";
  $("#s-zhipu").placeholder = s.has_zhipu_key ? "已配置（留空保持不变）" : "sk-…";
  // 环境卡（迭代27）
  const st = await api("/api/status");
  if (st.ok) {
    const dev = (st.system_stats?.devices || [])[0];
    $("#env-card").innerHTML = `
      <div class="row" style="justify-content:space-between">
        <span>版本 <b>${st.version || "?"}</b></span>
        <span class="muted">ComfyUI ${st.comfy_online ? "✓ 在线" : "✗ 离线"}</span>
      </div>
      <div class="row" style="justify-content:space-between">
        <span class="muted">ffmpeg：${st.ffmpeg ? "✓ 可用（视频海报帧）" : "✗ 未找到（视频无预览，其余可用）"}</span>
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
