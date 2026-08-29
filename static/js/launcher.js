/* launcher.js — 启动器：ComfyUI 生命周期 + 版本维护 + 模型管理 + 环境诊断 */
import { $, api, toast, fmtSize } from "./app.js";

let pollTimer = null;
let comfyHead = null;

export function initLauncher() {
  // 版本维护
  loadVersionInfo();
  $("#cv-check").addEventListener("click", checkRemote);
  $("#cv-update").addEventListener("click", doUpdate);
  $("#lc-start").addEventListener("click", async () => {
    const r = await api("/api/comfy/launch", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    setTimeout(poll, 4000);
  });
  $("#lc-restart").addEventListener("click", async () => {
    if (!confirm("重启 ComfyUI？（正在执行的任务会中断）")) return;
    const r = await api("/api/comfy/restart", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    setTimeout(poll, 6000);
  });
  $("#lc-stop").addEventListener("click", async () => {
    if (!confirm("停止 ComfyUI？（正在执行的任务会中断）")) return;
    const r = await api("/api/comfy/stop", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    setTimeout(poll, 2000);
  });
  $("#lc-log-refresh").addEventListener("click", loadLog);
  $("#lc-save").addEventListener("click", async () => {
    const r = await api("/api/settings", {
      method: "POST",
      body: { comfy_dir: $("#lc-dir").value.trim(), comfy_python: $("#lc-py").value.trim(),
              comfy_launch_args: $("#lc-args").value.trim() },
    });
    $("#lc-msg").textContent = r.ok ? "已保存" : r.error || "保存失败";
    toast(r.ok ? "启动配置已保存" : (r.error || "保存失败"), r.ok ? "ok" : "err");
  });
  // 设置页字段复用（配置读取）
  api("/api/settings").then((r) => {
    if (!r.ok) return;
    $("#lc-dir").value = r.settings.comfy_dir || "";
    $("#lc-py").value = r.settings.comfy_python || "";
    $("#lc-args").value = r.settings.comfy_launch_args || "";
  });
  poll();
  loadLog();
  // 页面可见时轮询
  new MutationObserver(() => {
    const active = $("#view-launcher").classList.contains("active");
    if (active && !pollTimer) { poll(); pollTimer = setInterval(poll, 4000); }
    if (!active && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }).observe($("#view-launcher"), { attributes: true, attributeFilter: ["class"] });
}

async function poll() {
  const r = await api("/api/launcher/info");
  if (!r.ok) return;
  const badge = $("#lc-state");
  badge.textContent = r.running ? `● 运行中（端口 ${r.port}）` : "● 已停止";
  badge.style.color = r.running ? "var(--ok)" : "var(--text-3)";
  $("#lc-start").disabled = r.running;
  // 诊断
  const d = r.disk;
  $("#lc-diag").innerHTML = `
    <div class="kv-line"><span>Python（后端）</span><b>${r.python_version}</b></div>
    <div class="kv-line"><span>ffmpeg</span><b>${r.ffmpeg ? "✓ 可用" : "✗ 未找到"}</b></div>
    <div class="kv-line"><span>成果盘剩余空间</span><b>${d ? fmtSize(d.free) + " / " + fmtSize(d.total) : "—"}</b></div>
    <div class="kv-line"><span>自定义节点</span><b>${r.nodes.length} 个</b></div>
    <div class="kv-line"><span>模型文件</span><b>${Object.values(r.models).reduce((a, m) => a + m.count, 0)} 个</b></div>`;
  // 模型
  const labels = { checkpoints: "大模型 Checkpoints", loras: "LoRA", vae: "VAE", upscale_models: "放大模型", controlnet: "ControlNet" };
  $("#lc-models").innerHTML = Object.entries(r.models).map(([sub, m]) => `
    <div class="card pad" style="margin-bottom:12px">
      <div class="row" style="justify-content:space-between;margin-bottom:8px">
        <h3 style="font-size:13px">${labels[sub] || sub} <span class="badge">${m.count} 个 · ${fmtSize(m.size)}</span></h3>
      </div>
      ${m.items.length ? `<div class="model-list">${m.items.map((i) =>
        `<div class="model-item" title="${i.name}"><span class="model-name">${i.name}</span><span class="muted">${fmtSize(i.size)}</span></div>`).join("")}
        ${m.count > m.items.length ? `<div class="muted" style="padding:6px 2px">…等 ${m.count} 个</div>` : ""}</div>`
        : `<div class="muted">（空）</div>`}
    </div>`).join("");
  // 节点
  $("#lc-nodes").innerHTML = r.nodes.length
    ? `<div class="chips">${r.nodes.map((n) => `<span class="chip" style="cursor:default">${n}</span>`).join("")}</div>`
    : `<div class="muted">（未找到 custom_nodes 目录）</div>`;
}

async function loadLog() {
  const r = await api("/api/comfy/log");
  if (r.ok) {
    const pre = $("#lc-log");
    pre.textContent = r.lines;
    pre.scrollTop = pre.scrollHeight;
  }
}

/* ---------- ComfyUI 版本维护 ---------- */
async function loadVersionInfo() {
  const info = $("#cv-version-info");
  const r = await api("/api/comfy/git");
  if (!r.ok) { info.textContent = "读取失败"; return; }
  if (!r.git) { info.innerHTML = "⚠ ComfyUI 目录不是 git 仓库，无法使用一键更新"; return; }
  comfyHead = r.head;
  info.innerHTML = `当前 <b>${r.head}</b>（${r.branch} 分支）· 界面版本 ${r.ui_version || "未运行"} · 本地改动 ${r.dirty_tracked} 个文件（更新时自动暂存恢复）`;
}

async function checkRemote() {
  const info = $("#cv-version-info");
  const old = info.innerHTML;
  info.innerHTML = "正在连接远端检查（首次 fetch 可能较慢）…";
  const r = await api("/api/comfy/check_remote");
  if (!r.ok) { info.innerHTML = old; toast(r.error, "err"); return; }
  info.innerHTML = r.behind > 0
    ? `当前 <b>${r.head}</b> · 远端有 <b style="color:var(--warn)">${r.behind}</b> 个新提交，可一键更新`
    : `已是最新 <b>${r.head}</b>（与远端一致）`;
}

async function doUpdate() {
  if (!confirm("一键更新 ComfyUI？\n· 本地改动会自动暂存并在更新后恢复\n· 更新后需要重启 ComfyUI 生效")) return;
  const info = $("#cv-version-info");
  info.innerHTML = "更新中（stash → pull → 恢复），可能需要一两分钟…";
  const r = await api("/api/comfy/update", { method: "POST", body: {} });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) {
    info.innerHTML = `✓ ${r.msg} ${r.note || ""}`;
    loadVersionInfo();
    if (confirm("ComfyUI 已更新。现在重启 ComfyUI 使新版本生效吗？")) {
      const rr = await api("/api/comfy/restart", { method: "POST", body: {} });
      toast(rr.msg || rr.error, rr.ok ? "ok" : "err");
      setTimeout(poll, 6000);
    }
  } else {
    info.innerHTML = "✗ " + (r.msg || r.error);
  }
}
