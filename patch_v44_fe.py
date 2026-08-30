# -*- coding: utf-8 -*-
"""v4.4 frontend patch: 集数视图/场景库/音频/优先级/字幕"""
def patch(path, pairs):
    src = open(path, encoding='utf-8').read()
    n = 0
    for tag, old, new in pairs:
        if old in src:
            src = src.replace(old, new, 1); n += 1
        else:
            print(f'STILL MISS [{tag}] in {path}')
    open(path, 'w', encoding='utf-8', newline='\n').write(src)
    print(path, '->', n, 'applied')

# ===== pipeline.js: 场景库 + 集数视图 + 优先级 + 字幕 =====
pairs = [
    ('init-new-handlers', '''  $("#pl-del").addEventListener("click", delBatch);''',
     '''  $("#pl-del").addEventListener("click", delBatch);
  $("#pl-episodes").addEventListener("click", toggleEpisodes);
  $("#pl-scenes").addEventListener("click", () => {
    const box = $("#scene-editor");
    if (box) box.hidden = !box.hidden;
  });'''),
]
patch('static/js/pipeline.js', pairs)

# ===== pipeline.js: 在文件末尾追加场景库/集数视图/字幕函数 =====
addition = '''

/* ---------- 场景库 ---------- */
let scenes = [];
let curScene = null;

async function loadScenes() {
  const r = await api("/api/scenes");
  if (!r.ok) return;
  scenes = r.scenes;
  const box = $("#scene-list");
  if (!box) return;
  box.innerHTML = scenes.length
    ? scenes.map((s) => `<div class="note-item" data-id="${s.id}"><span class="nm">🌐 ${s.name}</span><span class="meta">${(s.tokens || "").length}字</span></div>`).join("")
    : `<div class="muted">还没有场景。</div>`;
  box.querySelectorAll(".note-item").forEach((el) => el.addEventListener("click", () => editScene(el.dataset.id)));
}

function editScene(id) {
  const s = scenes.find((x) => x.id === id);
  if (!s) return;
  curScene = s;
  $("#scene-editor").hidden = false;
  $("#scene-name").value = s.name;
  $("#scene-desc").value = s.desc || "";
  $("#scene-tokens").value = s.tokens || "";
}

const sceneNewBtn = $("#scene-new");
if (sceneNewBtn) sceneNewBtn.addEventListener("click", () => {
  curScene = null; $("#scene-editor").hidden = false;
  $("#scene-name").value = ""; $("#scene-desc").value = ""; $("#scene-tokens").value = "";
});
const sceneSaveBtn = $("#scene-save");
if (sceneSaveBtn) sceneSaveBtn.addEventListener("click", async () => {
  const body = { name: $("#scene-name").value.trim(), desc: $("#scene-desc").value, tokens: $("#scene-tokens").value };
  if (!body.name) { toast("场景名必填", "err"); return; }
  if (curScene) body.id = curScene.id;
  const r = await api("/api/scenes/save", { method: "POST", body });
  toast(r.ok ? "场景已保存" : r.error, r.ok ? "ok" : "err");
  loadScenes();
});
const sceneDelBtn = $("#scene-del");
if (sceneDelBtn) sceneDelBtn.addEventListener("click", async () => {
  if (!curScene || !confirm(`删除场景？`)) return;
  await api("/api/scenes/delete", { method: "POST", body: { id: curScene.id } });
  curScene = null; $("#scene-editor").hidden = true; loadScenes();
});

/* ---------- 集数聚合视图 ---------- */
let episodesVisible = false;

function toggleEpisodes() {
  episodesVisible = !episodesVisible;
  $("#pl-episodes-view").hidden = !episodesVisible;
  $("#pl-detail-head").hidden = episodesVisible;
  $("#pl-items").innerHTML = episodesVisible ? "" : `<div class="muted">左侧选择批次，或导入分镜脚本新建</div>`;
  if (episodesVisible) renderEpisodes();
}

async function renderEpisodes() {
  const r = await api("/api/batches/episodes");
  if (!r.ok) return;
  const box = $("#pl-items");
  box.innerHTML = r.episodes.length
    ? `<div class="card pad"><h3 style="font-size:13px;margin-bottom:10px">📊 按集聚合</h3>
       ${r.episodes.map((e) => `<div class="pl-item">
           <b>${e.name}</b> · ${e.total} 镜 · ✓${e.done} ✗${e.failed} · ⏱${e.gpu_minutes.toFixed(1)}min
         </div>`).join("")}</div>`
    : `<div class="muted">没有批次</div>`;
}

/* ---------- 字幕烧入 ---------- */
const subBtn = $("#pl-subtitle");
if (subBtn) subBtn.addEventListener("click", async () => {
  const video = prompt("视频文件路径（output 相对路径）：");
  const srt = prompt("SRT 字幕文件路径：");
  if (!video || !srt) return;
  const r = await api("/api/subtitle_burn", { method: "POST", body: { video, srt_path: srt } });
  toast(r.ok ? "字幕已烧入 → " + r.output : r.error, r.ok ? "ok" : "err");
});
'''
open('static/js/pipeline.js', 'a', encoding='utf-8').write(addition)
print('pipeline.js additions written')

# ===== style.css: 场景库样式 =====
css_add = '''

/* ---------- 场景库/集数 ---------- */
#scene-list .note-item, #audio-list .note-item { font-size: 12px; }
#audio-list audio { width: 100%; margin-top: 4px; }
'''
open('static/style.css', 'a', encoding='utf-8').write(css_add)
print('css done')
INNEREOF
