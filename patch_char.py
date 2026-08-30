# -*- coding: utf-8 -*-
p = 'static/js/pipeline.js'
src = open(p, encoding='utf-8').read()
n = 0

old = '''function editChar(id) {
  const c = characters.find((x) => x.id === id);
  if (!c) return;
  curChar = c;
  $("#char-editor").hidden = false;
  $("#char-name").value = c.name; $("#char-lock").value = c.lock || ""; $("#char-ref").value = c.ref || "";
  updateRefPreview(c.ref);
}'''
new = '''function editChar(id) {
  const c = characters.find((x) => x.id === id);
  if (!c) return;
  curChar = c;
  $("#char-editor").hidden = false;
  $("#char-name").value = c.name; $("#char-lock").value = c.lock || ""; $("#char-ref").value = c.ref || "";
  updateRefPreview(c.ref);
  renderCharThumbs(c.refs && c.refs.length ? c.refs : (c.ref ? [c.ref] : []));
}

function renderCharThumbs(refs) {
  const box = $("#char-refs-thumbs");
  if (!box) return;
  box.innerHTML = (refs || []).map((r, i) =>
    `<div style="position:relative"><img src="/api/media?path=${encodeURIComponent(r)}&thumb=1" style="height:60px;border-radius:8px">
     <button class="btn sm danger ghost" data-i="${i}" style="position:absolute;top:-6px;right:-6px;padding:0 6px">✕</button></div>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
    refs.splice(+b.dataset.i, 1);
    $("#char-ref").dataset.refs = refs.join("|");
    $("#char-ref").value = refs[0] || "";
    renderCharThumbs(refs);
  }));
}'''
if old in src: src = src.replace(old, new, 1); n += 1
else: print('MISS char-multi-fn')

old = '''  $("#char-pick").addEventListener("click", () => openPicker("选择角色参考图（定妆照/三视图）", (path) => {
    $("#char-ref").value = path;
    updateRefPreview(path);
  }));'''
new = '''  $("#char-pick").addEventListener("click", () => openPicker("选择角色参考图（可多选，最多4张）", (path) => {
    let refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
    if (!refs.includes(path)) refs.push(path);
    refs = refs.slice(0, 4);
    $("#char-ref").dataset.refs = refs.join("|");
    $("#char-ref").value = refs[0] || "";
    updateRefPreview(path);
    renderCharThumbs(refs);
  }));'''
if old in src: src = src.replace(old, new, 1); n += 1
else: print('MISS char-pick-multi')

old = '''async function saveChar() {
  const body = { name: $("#char-name").value.trim(), lock: $("#char-lock").value, ref: $("#char-ref").value.trim() };'''
new = '''async function saveChar() {
  const refs = ($("#char-ref").dataset.refs || "").split("|").filter(Boolean);
  const body = { name: $("#char-name").value.trim(), lock: $("#char-lock").value,
                 ref: refs[0] || $("#char-ref").value.trim(), refs };'''
if old in src: src = src.replace(old, new, 1); n += 1
else: print('MISS char-save-refs')

open(p, 'w', encoding='utf-8', newline='\n').write(src)
print('applied', n, '/3')
