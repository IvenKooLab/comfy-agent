# -*- coding: utf-8 -*-
"""草稿/成片双档体系：H3 T8/PDD 研究成果产品化。
server 注入 tier/est_min + 草稿映射；创作页动态预估；产线草稿快跑按钮；i18n/帮助页。"""
import io, json, glob, re

# ============ 1) server.py：WF_META 注入 + DRAFT_MAP + run_batch(draft) + 路由 ============
f = 'server.py'
s = io.open(f, encoding='utf-8').read()

# 1a. 常量表：放 list_workflows 定义前
anchor = 'def list_workflows():'
assert s.count(anchor) == 1
meta = '''# H3 档位元数据（实测值来自 minimax-h3-turing 研究会话，代码侧注入避免改动工作流 json 文件）
# tier: final=成片（同 seed 可复现） draft=草稿（T8 缓存命中致采样分叉，同 seed 不可复现）
WF_META = {
    "builtin-flux": {"tier": "final", "est_min": 1.5},
    "h3-t2v": {"tier": "final", "est_min": 4.7},
    "h3-i2v": {"tier": "final", "est_min": 7.0},
    "h3-t2v-t8draft": {"tier": "draft", "est_min": 2.7},
    "h3-i2v-t8draft": {"tier": "draft", "est_min": 4.3},
    "h3-t2v-pdd8-t8": {"tier": "draft", "est_min": 3.5},
}
# 草稿快跑映射：成片工作流 → 对应草稿档（PDD8 版需 master+PDD 权重，留手动选择）
DRAFT_MAP = {"h3-t2v": "h3-t2v-t8draft", "h3-i2v": "h3-i2v-t8draft"}


''' + anchor
s = s.replace(anchor, meta)

# 1b. list_workflows 注入元数据
old = '''    out.sort(key=lambda w: (w.get("builtin", False) is False, w.get("name", "")))
    return out'''
assert s.count(old) == 1
s = s.replace(old, '''    out.sort(key=lambda w: (w.get("builtin", False) is False, w.get("name", "")))
    for w in out:
        m = WF_META.get(w.get("id"))
        if m:
            w.update(m)
    return out''')

# 1c. run_batch 支持 draft
old = 'def run_batch(bid, only_index=None):\n    b = _load_batch(bid)'
assert s.count(old) == 1
s = s.replace(old, '''def run_batch(bid, only_index=None, draft=False):
    b = _load_batch(bid)''')

old = '''    wf = None
    for w in list_workflows():
        if w.get("id") == b.get("workflow_id"):
            wf = w
            break'''
assert s.count(old) == 1
s = s.replace(old, '''    wf_id = b.get("workflow_id")
    if draft and wf_id in DRAFT_MAP:
        wf_id = DRAFT_MAP[wf_id]  # 草稿快跑：映射到对应 T8 草稿档（同 seed 不可复现，仅选镜用）
    wf = None
    for w in list_workflows():
        if w.get("id") == wf_id:
            wf = w
            break''')

# 1d. 路由透传 draft
old = '''        if path == "/api/batches/run" and method == "POST":
            return self.send_json(run_batch(body.get("id", "")))'''
assert s.count(old) == 1
s = s.replace(old, '''        if path == "/api/batches/run" and method == "POST":
            return self.send_json(run_batch(body.get("id", ""), draft=bool(body.get("draft"))))''')
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('server.py ok')

# ============ 2) i18n.js：WF_EN 补全 + wfLabel 草稿后缀 + 新 key ============
f = 'static/js/i18n.js'
s = io.open(f, encoding='utf-8').read()

old = '''  "h3-t2v": "H3 t2v W4A8 · 4-step fast lane (640×352)",
  "h3-i2v": "H3 i2v W4A8 · 4-step fast lane (640×352)",
  "h3-t2v-t8draft": "H3 t2v T8 draft (fast, -43%, non-reproducible)",'''
assert s.count(old) == 1
s = s.replace(old, '''  "h3-t2v": "H3 t2v W4A8 · 4-step fast lane (640×352)",
  "h3-i2v": "H3 i2v W4A8 · 4-step fast lane (640×352)",
  "h3-t2v-t8draft": "H3 t2v T8 draft (fast, -43%, non-reproducible)",
  "h3-i2v-t8draft": "H3 i2v T8 draft (-38%, non-reproducible)",
  "h3-t2v-pdd8-t8": "H3 t2v PDD8+T8 (fastest, master env, non-reproducible)",''')

# wfLabel：草稿档加 ⚡ 后缀（下拉/列表通用）
old = '''export function wfLabel(w) {
  return (lang === "en" && WF_EN[w.id]) ? WF_EN[w.id] : (w.name || w.id || "");
}'''
assert s.count(old) == 1
s = s.replace(old, '''export function wfLabel(w) {
  const base = (lang === "en" && WF_EN[w.id]) ? WF_EN[w.id] : (w.name || w.id || "");
  return w.tier === "draft" ? base + (lang === "en" ? " ⚡draft" : " ⚡草稿") : base;
}''')

# 新 key
anchor = '  "pl.chain.tip":'
assert s.count(anchor) == 1
s = s.replace(anchor, '''  "pl.run.draft": ["⚡ 草稿快跑", "⚡ Draft run"],
  "pl.run.draft.tip": ["用 T8 草稿档快跑全部镜头（更快，适合选镜）；选镜后点单镜 ↻ 即用成片档重跑", "Draft-run all shots on the T8 lane (faster, for shot picking); then click per-shot ↻ to re-render keepers on the final lane"],
  "pl.run.draft.confirm": ["草稿快跑 %n 个镜头（约 %m 分钟）？\\nT8 缓存会让同 seed 不可复现——仅用于选镜，成片请跑完后点单镜 ↻ 重跑。", "Draft-run %n shots (~%m min)?\\nT8 caching makes seeds non-reproducible — for shot picking only. Re-run keepers with per-shot ↻ on the final lane."],
  "create.hint.draft": ["⚡ 草稿档 · 约 %m 分钟/条 · 同 seed 不可复现，勿用于成片", "⚡ Draft lane · ~%m min/clip · non-reproducible, not for final renders"],
  "create.hint.est": ["%s · 约 %m 分钟/条（视队列而定）", "%s · ~%m min/clip (queue dependent)"],
''' + anchor)
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('i18n.js ok')

# ============ 3) create.js：hint 随工作流动态化 ============
f = 'static/js/create.js'
s = io.open(f, encoding='utf-8').read()
old = '''function applyMode() {'''
assert s.count(old) == 1
hint_fn = '''/* 预估提示随所选工作流动态化（est_min/tier 由服务端注入） */
function updateHint() {
  const sel = $("#c-wf");
  const hint = $("#c-hint");
  if (!sel || !hint) return;
  const wf = workflows.find((w) => (w.id || w.name) === sel.value);
  if (!wf || wf.est_min == null) {
    hint.innerHTML = `<span class="dot2"></span>${mode === "video" ? VIDEO_HINT() : IMAGE_HINT()}`;
    return;
  }
  if (wf.tier === "draft") {
    hint.innerHTML = `<span class="dot2"></span>${tf("create.hint.draft", wf.est_min)}`;
  } else {
    hint.innerHTML = `<span class="dot2"></span>${tf("create.hint.est", mode === "video" ? "H3 W4A8 · 640×352 · ≈5s · 4步 · 原生音频" : "Flux 文生图 · 20步", wf.est_min)}`;
  }
}

''' + old
s = s.replace(old, hint_fn)

# 工作流下拉 change 时刷新 hint（找 loadWorkflows→applyMode 里 sel 绑定处）
old = '''  const sel = $("#c-wf");'''
cnt = s.count(old)
assert cnt >= 1, cnt
# 只在 applyMode 内的首次出现后追加绑定（定位 applyMode 块内的绑定：跟随尺寸分段注释）
old2 = '''  // 工作流过滤 + 尺寸显隐 + 预估提示
  const sel = $("#c-wf");'''
assert s.count(old2) == 1
s = s.replace(old2, '''  // 工作流过滤 + 尺寸显隐 + 预估提示
  const sel = $("#c-wf");
  sel.addEventListener("change", updateHint);''')
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('create.js ok')

# ============ 4) 产线：⚡ 草稿快跑按钮 ============
f = 'static/index.html'
s = io.open(f, encoding='utf-8').read()
old = '''              <button id="pl-run" class="btn primary" data-i18n="pl.run">▶ 排队全部</button>'''
assert s.count(old) == 1
s = s.replace(old, '''              <button id="pl-run" class="btn primary" data-i18n="pl.run" data-i18n-title="tip.pl.run">▶ 排队全部</button>
              <button id="pl-run-draft" class="btn" data-i18n="pl.run.draft" data-i18n-title="pl.run.draft.tip" hidden>⚡ 草稿快跑</button>''')
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('index.html ok')

f = 'static/js/pipeline.js'
s = io.open(f, encoding='utf-8').read()

# 绑定（initPipeline 里 pl-run 之后）
old = '''  $("#pl-run").addEventListener("click", runBatch);'''
assert s.count(old) == 1
s = s.replace(old, old + '''
  $("#pl-run-draft").addEventListener("click", () => runBatch(true));''')

# runBatch(draft)：confirm 文案 + POST draft 标志 + 按钮显隐
old = '''async function runBatch() {'''
# 找到现有实现（可能是 async function runBatch() { ... cur.items ...）
m = re.search(r'async function runBatch\(\) \{[\s\S]*?\n\}', s)
assert m, "runBatch not found"
fn = m.group(0)
new_fn = fn.replace('async function runBatch() {', 'async function runBatch(draft = false) {')
# confirm 替换
old_confirm = re.search(r'if \(!confirm\(tf\("pl\.queue\.all", cur\.items\.length\)\)\) return;', new_fn)
assert old_confirm, "confirm line not found"
new_fn = new_fn.replace('if (!confirm(tf("pl.queue.all", cur.items.length))) return;',
    'const est = draft ? (DRAFT_EST[cur.workflow_id] || 3) : 8.5;\n'
    '  if (!confirm(draft ? tf("pl.run.draft.confirm", cur.items.length, Math.ceil(cur.items.length * est))\n'
    '                    : tf("pl.queue.all", cur.items.length))) return;')
# POST body 加 draft
old_body = re.search(r'await api\("/api/batches/run", \{ method: "POST", body: \{ id: cur\.id \} \}\)', new_fn)
if old_body:
    new_fn = new_fn.replace('await api("/api/batches/run", { method: "POST", body: { id: cur.id } })',
                            'await api("/api/batches/run", { method: "POST", body: { id: cur.id, draft } })')
else:
    # 兜底：查看实际 body 形态
    raise SystemExit("runBatch POST body 形态与预期不符:\n" + fn)
new_fn = new_fn.replace('function runBatch(draft = false) {', 'function runBatch(draft = false) {')
s = s.replace(fn, new_fn)

# DRAFT_EST 常量 + 批次头显隐（openBatch 渲染处）：加在 chainFromPrev 定义前
anchor = '/* 镜头接龙：抽上一镜（最近一个成功且带输出的）末帧，设为本镜 i2v 首帧 */'
assert s.count(anchor) == 1
s = s.replace(anchor, '''/* 草稿档预估（分钟/镜，与研究实测一致）；成片档 8.5 为保守值 */
const DRAFT_EST = { "h3-t2v": 2.7, "h3-i2v": 4.3 };

''' + anchor)
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('pipeline.js runBatch ok')

# openBatch/renderItems：h3 批次显示草稿按钮——挂在 renderItems 开头（每次渲染同步显隐）
old = '''function renderItems() {
  const box = $("#pl-items");'''
assert s.count(old) == 1, "renderItems anchor"
s = s.replace(old, '''function renderItems() {
  const box = $("#pl-items");
  const draftBtn = $("#pl-run-draft");
  if (draftBtn) draftBtn.hidden = !cur || !DRAFT_MAP_FE[cur.workflow_id];''')

# 前端映射表（与 server DRAFT_MAP 对应，用于显隐与预估）
anchor = '/* 草稿档预估（分钟/镜，与研究实测一致）；成片档 8.5 为保守值 */\nconst DRAFT_EST = { "h3-t2v": 2.7, "h3-i2v": 4.3 };'
assert s.count(anchor) == 1, "DRAFT_EST anchor"
s = s.replace(anchor, 'const DRAFT_MAP_FE = { "h3-t2v": "h3-t2v-t8draft", "h3-i2v": "h3-i2v-t8draft" };\n' + anchor)
io.open(f, 'w', encoding='utf-8', newline='').write(s)
print('pipeline.js draft button ok')
