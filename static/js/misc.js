/* misc.js — Obsidian 知识库页 + 智能助手页 + 设置页 */
import { $, $$, api, toast, goto } from "./app.js";

export function initMisc() {
  initObsidian();
  initAgent();
  initSettings();
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
function initAgent() {
  const log = $("#chat-log");
  const say = (text, who = "bot", actions = null) => {
    const el = document.createElement("div");
    el.className = `msg ${who}`;
    el.textContent = text;
    if (actions?.length) {
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
  };
  say("你好，我是创作台助手。直接说人话就行：\n· 「画：雪夜竹林里的剑客 832x1216」\n· 「跑 Flux 文生图 ×3」\n· 「归档最近 10 个」\n· 「状态 / 中断 / 清空队列」", "bot");

  const send = async () => {
    const text = $("#chat-input").value.trim();
    if (!text) return;
    $("#chat-input").value = "";
    say(text, "user");
    const holder = document.createElement("div");
    holder.className = "msg bot"; holder.textContent = "思考中…";
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
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
