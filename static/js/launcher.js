/* launcher.js — 启动器：ComfyUI 生命周期 + 版本维护 + 模型管理 + 环境诊断 */
import { $, api, toast, fmtSize } from "./app.js";
import { t, tf } from "./i18n.js";

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
    if (!confirm(t("misc.confirm.restart"))) return;
    const r = await api("/api/comfy/restart", { method: "POST", body: {} });
    toast(r.msg || r.error, r.ok ? "ok" : "err");
    setTimeout(poll, 6000);
  });
  $("#lc-stop").addEventListener("click", async () => {
    if (!confirm(t("misc.confirm.stop"))) return;
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
    $("#lc-msg").textContent = r.ok ? t("toast.saved") : r.error || t("toast.save.fail");
    toast(r.ok ? t("toast.comfy.saved") : (r.error || t("toast.save.fail")), r.ok ? "ok" : "err");
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
  badge.textContent = r.running ? tf("lc.running", r.port) : t("lc.stopped");
  badge.style.color = r.running ? "var(--ok)" : "var(--text-3)";
  $("#lc-start").disabled = r.running;
  // 诊断
  const d = r.disk;
  $("#lc-diag").innerHTML = `
    <div class="kv-line"><span>${t("lc.python")}</span><b>${r.python_version}</b></div>
    <div class="kv-line"><span>torch / triton / sage</span><b>${[r.ai_env && (r.ai_env.torch || r.ai_env["torch"]), r.ai_env && r.ai_env["triton-windows"], r.ai_env && r.ai_env.sageattention].map(v => v || "—").join(" / ")}</b></div>
    <div class="kv-line"><span>ffmpeg</span><b>${r.ffmpeg ? t("lc.ok") : t("lc.missing")}</b></div>
    <div class="kv-line"><span>${t("lc.disk")}</span><b>${d ? fmtSize(d.free) + " / " + fmtSize(d.total) : "—"}</b></div>
    <div class="kv-line"><span>${t("lc.nodes")}</span><b>${r.nodes.length}${t("unit.count")}</b></div>
    <div class="kv-line"><span>${t("lc.models")}</span><b>${Object.values(r.models).reduce((a, m) => a + m.count, 0)}${t("unit.count")}</b></div>`;
  // 模型
  const labels = { checkpoints: t("lc.m.checkpoints"), loras: t("lc.m.loras"), vae: t("lc.m.vae"), upscale_models: t("lc.m.upscale_models"), controlnet: t("lc.m.controlnet") };
  $("#lc-models").innerHTML = Object.entries(r.models).map(([sub, m]) => `
    <div class="card pad" style="margin-bottom:12px">
      <div class="row" style="justify-content:space-between;margin-bottom:8px">
        <h3 style="font-size:13px">${labels[sub] || sub} <span class="badge">${m.count}${t("unit.count")} · ${fmtSize(m.size)}</span></h3>
      </div>
      ${m.items.length ? `<div class="model-list">${m.items.map((i) =>
        `<div class="model-item" title="${i.name}"><span class="model-name">${i.name}</span><span class="muted">${fmtSize(i.size)}</span></div>`).join("")}
        ${m.count > m.items.length ? `<div class="muted" style="padding:6px 2px">${tf("lc.more", m.count)}</div>` : ""}</div>`
        : `<div class="muted">${t("empty.paren")}</div>`}
    </div>`).join("");
  // 节点
  $("#lc-nodes").innerHTML = r.nodes.length
    ? `<div class="chips">${r.nodes.map((n) => `<span class="chip" style="cursor:default">${n}</span>`).join("")}</div>`
    : `<div class="muted">${t("lc.nodir")}</div>`;
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
  if (!r.ok) { info.textContent = "Load failed"; return; }
  if (!r.git) { info.innerHTML = "⚠ Not a git repo, one-click update unavailable"; return; }
  comfyHead = r.head;
  info.innerHTML = tf("lc.ver.line", r.head, r.branch, r.ui_version || t("lc.uinotrun"), r.dirty_tracked);
}

async function checkRemote() {
  const info = $("#cv-version-info");
  const old = info.innerHTML;
  info.innerHTML = "Checking remote (first fetch may be slow)…";
  const r = await api("/api/comfy/check_remote");
  if (!r.ok) { info.innerHTML = old; toast(r.error, "err"); return; }
  info.innerHTML = r.behind > 0
    ? tf("lc.behind", r.head, r.behind)
    : tf("lc.uptodate", r.head);
}

async function doUpdate() {
  if (!confirm(t("misc.confirm.update"))) return;
  const info = $("#cv-version-info");
  info.innerHTML = t("lc.updating");
  const r = await api("/api/comfy/update", { method: "POST", body: {} });
  toast(r.msg || r.error, r.ok ? "ok" : "err");
  if (r.ok) {
    info.innerHTML = `✓ ${r.msg} ${r.note || ""}`;
    loadVersionInfo();
    if (confirm(t("lc.updated.ask"))) {
      const rr = await api("/api/comfy/restart", { method: "POST", body: {} });
      toast(rr.msg || rr.error || t("status.offline"), rr.ok ? "ok" : "err");
      setTimeout(poll, 6000);
    }
  } else {
    info.innerHTML = "✗ " + (r.msg || r.error);
  }
}
