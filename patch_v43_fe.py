# -*- coding: utf-8 -*-
"""v4.3 frontend patch: 产线表格化/BGM/账本 + 角色多图 + 反推按钮 + 模板收藏 + 设置新项"""
import sys

def patch(path, pairs):
    src = open(path, encoding='utf-8').read()
    miss = []
    for tag, old, new in pairs:
        if old in src:
            src = src.replace(old, new, 1)
        else:
            miss.append(tag)
    open(path, 'w', encoding='utf-8', newline='\n').write(src)
    print(path, '-> applied', len(pairs) - len(miss), '| MISS:', miss if miss else '无')

# ============ pipeline.js ============
pairs = []
# 提示词可编辑 + 重试徽标 + 关键帧状态
pairs.append(('render-textarea', '''    return `<div class="pl-item">
      <span class="run-status ${cls}">${txt}</span>
      <input class="input pl-item-name" data-i="${i}" value="${it.name.replace(/"/g, "&quot;")}">
      ${ff}
      <button class="btn sm ghost pl-retry" data-i="${i}" title="单独重试这一镜">↻</button>
    </div>
    <div class="pl-prompt" data-i="${i}">${it.prompt.slice(0, 220)}${it.prompt.length > 220 ? "…" : ""}</div>`;''',
'''    const retryN = it.retry_count ? ` <span class="muted">↻${it.retry_count}</span>` : "";
    return `<div class="pl-item">
      <span class="run-status ${cls}">${txt}</span>
      <input class="input pl-item-name" data-i="${i}" value="${it.name.replace(/"/g, "&quot;")}">
      ${ff}
      <button class="btn sm ghost pl-retry" data-i="${i}" title="单独重试这一镜">↻</button>
    </div>
    <textarea class="input pl-prompt-edit" data-i="${i}" rows="2">${it.prompt.replace(/"/g, "&quot;").replace(/</g, "&lt;")}</textarea>`;'''))
# 提示词编辑保存事件
pairs.append(('prompt-edit-event', '''  box.querySelectorAll(".pl-retry").forEach((b) => b.addEventListener("click", async () => {''',
'''  box.querySelectorAll(".pl-prompt-edit").forEach((ta) => ta.addEventListener("change", (e) => {
    cur.items[+e.target.dataset.i].prompt = e.target.value;
    saveBatch(true);
    toast("提示词已更新", "ok");
  }));
  box.querySelectorAll(".pl-retry").forEach((b) => b.addEventListener("click", async () => {'''))
# BGM 输入行 + 账本（detail head）
pairs.append(('bgm-ledger-html', '''          <div class="row" style="justify-content:space-between">
              <input id="pl-name" class="input grow" placeholder="批次名">
              <select id="pl-wf" class="input select"></select>
              <button id="pl-save" class="btn">保存</button>
              <button id="pl-run" class="btn primary">▶ 排队全部</button>
              <button id="pl-concat" class="btn">🎬 拼接成片</button>
              <button id="pl-del" class="btn danger ghost">删除</button>
            </div>''',
'''          <div class="row" style="justify-content:space-between">
              <input id="pl-name" class="input grow" placeholder="批次名">
              <select id="pl-wf" class="input select"></select>
              <button id="pl-save" class="btn">保存</button>
              <button id="pl-run" class="btn primary">▶ 排队全部</button>
              <button id="pl-concat" class="btn">🎬 拼接成片</button>
              <button id="pl-del" class="btn danger ghost">删除</button>
            </div>
            <div class="row margin-top" style="flex-wrap:wrap">
              <span class="muted">BGM（可选）：</span>
              <input id="pl-bgm" class="input" style="width:280px" placeholder="背景音乐文件路径（mp3/wav）">
              <span class="muted">音量</span>
              <input id="pl-bgm-vol" class="input" type="number" min="0" max="1" step="0.05" value="0.25" style="width:70px">
              <span id="pl-ledger" class="muted"></span>
            </div>'''))
# concat 传 BGM
pairs.append(('concat-bgm', '''  const r = await api("/api/concat", { method: "POST", body: { paths: outs, name: cur.name } });
  concatBusy = false;''',
'''  const bgm = $("#pl-bgm") ? $("#pl-bgm").value.trim() : "";
  const vol = $("#pl-bgm-vol") ? parseFloat($("#pl-bgm-vol").value) || 0.25 : 0.25;
  const r = await api("/api/concat", { method: "POST", body: { paths: outs, name: cur.name, bgm, bgm_volume: vol } });
  concatBusy = false;'''))
# 账本：批次打开时计算总渲染时长
pairs.append(('ledger-calc', '''  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = cur.name;
  await fillWfSelect();
  renderItems();
  refresh();''',
'''  $("#pl-detail-head").hidden = false;
  $("#pl-name").value = cur.name;
  const mins = (cur.items || []).filter((i) => i.duration).reduce((a, i) => a + i.duration, 0);
  const done = (cur.items || []).filter((i) => i.status === "success").length;
  $("#pl-ledger").textContent = `⏱ GPU 已用 ${mins.toFixed(1)} 分钟 · 成功 ${done}/${cur.items.length}`;
  await fillWfSelect();
  renderItems();
  refresh();'''))
patch('static/js/pipeline.js', pairs)

# ============ index.html（产线 BGM 已含；角色编辑器预览图/多图提示） ============
pairs = []
pairs.append(('char-multi-hint', '''          <div class="field"><label>参考图（定妆照/三视图，从画廊选择）</label>''',
'''          <div class="field"><label>参考图（定妆照/三视图，最多4张；点击缩略图可移除）</label>
            <div id="char-refs-thumbs" class="row" style="gap:6px;margin-bottom:6px"></div>'''))
patch('static/index.html', pairs)

# ============ gallery.js（灯箱反推提示词） ============
pairs = []
pairs.append(('lb-i2p-btn', '''      <button class="btn" id="lb-archive" data-i18n="lb.archive">归档到知识库</button>''',
'''      <button class="btn" id="lb-archive" data-i18n="lb.archive">归档到知识库</button>
      <button class="btn" id="lb-i2p">🔍 反推提示词</button>'''))
pairs.append(('lb-i2p-handler', '''  $("#lb-archive").addEventListener("click", doArchive);''',
'''  $("#lb-archive").addEventListener("click", doArchive);
  // 图生文反推：视觉 LLM 从图生成英文提示词
  $("#lb-i2p").addEventListener("click", async () => {
    const it = visible()[lbIndex];
    if (!it || it.kind !== "image") { toast("仅图片支持反推", "err"); return; }
    const btn = $("#lb-i2p");
    btn.disabled = true; btn.textContent = "反推中…";
    try {
      const r = await api("/api/image_to_prompt", { method: "POST", body: { path: it.path } });
      if (r.ok && r.prompt) {
        const box = $("#lb-summary");
        box.innerHTML = `<div class="kv"><span>反推</span><span class="kv-val">${r.prompt.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span></div>
          <button class="kv-copy" id="lb-i2p-copy">复制</button>`;
        box.querySelector("#lb-i2p-copy").addEventListener("click", () => {
          navigator.clipboard.writeText(r.prompt).then(() => { btn.textContent = "✓ 已复制"; setTimeout(() => btn.textContent = "复制", 1200); });
        });
      } else toast(r.error, "err");
    } finally {
      btn.disabled = false; btn.textContent = "🔍 反推提示词";
    }
  });'''))
patch('static/js/gallery.js', pairs)

# ============ templates.js（收藏） ============
pairs = []
pairs.append(('fav-state', '''let groups = [];
let curGroup = "all";
let q = "";
let shown = 24;
let importing = false;''',
'''let groups = [];
let curGroup = localStorage.getItem("tpl_fav_only") === "1" ? "fav" : "all";
let q = "";
let shown = 24;
let importing = false;
let favs = JSON.parse(localStorage.getItem("tpl_favs") || "[]");'''))
pairs.append(('fav-chip', '''  $("#tpl-search").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); shown = 24; renderCards(); });''',
'''  $("#tpl-search").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); shown = 24; renderCards(); });
  const favChip = document.createElement("button");
  favChip.className = "chip" + (curGroup === "fav" ? " active" : "");
  favChip.textContent = "⭐ 只看收藏";
  favChip.addEventListener("click", () => {
    curGroup = curGroup === "fav" ? "all" : "fav";
    favChip.classList.toggle("active", curGroup === "fav");
    shown = 24; renderCards();
  });
  document.querySelector(".page-head .head-tools").prepend(favChip);'''))
pairs.append(('fav-filter', '''  const list = all.filter((t) => {
    if (curGroup !== "all" && t.group !== curGroup) return false;''',
'''  const list = all.filter((t) => {
    if (curGroup === "fav" && !favs.includes(t.name)) return false;
    if (curGroup !== "all" && curGroup !== "fav" && t.group !== curGroup) return false;'''))
pairs.append(('fav-star', '''    const preview = `/api/templates/preview?name=${encodeURIComponent(t.name)}&ext=${t.mediaSubtype || "webp"}`;''',
'''    const preview = `/api/templates/preview?name=${encodeURIComponent(t.name)}&ext=${t.mediaSubtype || "webp"}`;
    const isFav = favs.includes(t.name);'''))
pairs.append(('fav-star2', '''      <div class="tpl-thumb"><div class="tpl-ph"><span>${t.title.slice(0, 1)}</span></div>
        <img class="tpl-img" src="${preview}" loading="lazy" onerror="this.remove()">
        <div class="tpl-badges">${badge}${tags}</div></div>''',
'''      <div class="tpl-thumb"><div class="tpl-ph"><span>${t.title.slice(0, 1)}</span></div>
        <img class="tpl-img" src="${preview}" loading="lazy" onerror="this.remove()">
        <button class="tpl-fav" data-n="${t.name}">${isFav ? "★" : "☆"}</button>
        <div class="tpl-badges">${badge}${tags}</div></div>'''))
pairs.append(('fav-toggle', '''    card.addEventListener("click", () => openTemplate(t));''',
'''    card.querySelector(".tpl-fav").addEventListener("click", (e) => {
      e.stopPropagation();
      const n = e.target.dataset.n;
      favs = favs.includes(n) ? favs.filter((x) => x !== n) : [...favs, n];
      localStorage.setItem("tpl_favs", JSON.stringify(favs));
      e.target.textContent = favs.includes(n) ? "★" : "☆";
    });
    card.addEventListener("click", () => openTemplate(t));'''))
patch('static/js/templates.js', pairs)

# ============ misc.js（设置：自动重试次数/局域网） ============
pairs = []
pairs.append(('set-html', '''        <label style="flex-direction:row;align-items:center;gap:8px"><input id="s-autorequeue" type="checkbox" style="width:auto"> 重启后自动续跑中断任务（按图快照同种子重提）</label>''',
'''        <label style="flex-direction:row;align-items:center;gap:8px"><input id="s-autorequeue" type="checkbox" style="width:auto"> 重启后自动续跑中断任务（按图快照同种子重提）</label>
        <label style="flex-direction:row;align-items:center;gap:8px"><input id="s-lan" type="checkbox" style="width:auto"> 允许局域网设备访问（重启生效，注意安全）</label>
        <label style="flex-direction:row;align-items:center;gap:8px">失败自动重试次数 <input id="s-batch-retry" type="number" min="0" max="5" style="width:70px"></label>'''))
pairs.append(('set-load', '''  $("#s-watchdog").checked = s.comfy_watchdog !== false;
  $("#s-autorequeue").checked = s.comfy_autorequeue !== false;''',
'''  $("#s-watchdog").checked = s.comfy_watchdog !== false;
  $("#s-autorequeue").checked = s.comfy_autorequeue !== false;
  $("#s-lan").checked = !!s.lan_access;
  $("#s-batch-retry").value = s.batch_auto_retry != null ? s.batch_auto_retry : 2;'''))
pairs.append(('set-save', '''      comfy_watchdog: $("#s-watchdog").checked,
      comfy_autorequeue: $("#s-autorequeue").checked,''',
'''      comfy_watchdog: $("#s-watchdog").checked,
      comfy_autorequeue: $("#s-autorequeue").checked,
      lan_access: $("#s-lan").checked,
      batch_auto_retry: parseInt($("#s-batch-retry").value) || 0,'''))
patch('static/js/misc.js', pairs)

print('ALL FRONTEND PATCHES DONE')
