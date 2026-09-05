/* ui.js — 暗色确认/输入弹窗（替换原生 confirm/prompt，风格与全站一致） */
import { $, $$ } from "./app.js";
import { t } from "./i18n.js";

let dlg = null;

function ensure() {
  if (dlg) return dlg;
  dlg = document.createElement("div");
  dlg.id = "ui-dialog";
  dlg.hidden = true;
  dlg.innerHTML = `
    <div class="uid-card">
      <div class="uid-msg"></div>
      <input class="input uid-input" hidden>
      <div class="row uid-btns" style="justify-content:flex-end;margin-top:16px">
        <button class="btn ghost uid-cancel"></button>
        <button class="btn primary uid-ok"></button>
      </div>
    </div>`;
  document.body.appendChild(dlg);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) settle(null); });
  dlg.querySelector(".uid-cancel").addEventListener("click", () => settle(null));
  dlg.querySelector(".uid-ok").addEventListener("click", () => settle(true));
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "Escape") settle(null);
    if (e.key === "Enter") settle(dlg._input.hidden ? true : dlg._input.value);
  });
  return dlg;
}

let _settle = null;
function settle(v) {
  if (!_settle) return;
  const s = _settle;
  _settle = null;
  dlg.hidden = true;
  dlg._input.blur();
  s(v);
}

function open({ msg, input = null, okText, danger }) {
  const d = ensure();
  d.querySelector(".uid-msg").textContent = msg;
  const inp = d.querySelector(".uid-input");
  inp.hidden = !input;
  if (input) { inp.value = input.value || ""; inp.placeholder = input.placeholder || ""; }
  d.querySelector(".uid-cancel").textContent = t("act.cancel");
  const ok = d.querySelector(".uid-ok");
  ok.textContent = okText || t("act.confirm");
  ok.classList.toggle("danger", !!danger);
  ok.classList.toggle("primary", !danger);
  d.hidden = false;
  setTimeout(() => (input ? inp : ok).focus(), 30);
}

export function uiConfirm(msg, { okText, danger = true } = {}) {
  return new Promise((resolve) => {
    _settle = (v) => resolve(v === true);
    open({ msg, okText, danger });
  });
}

export function uiPrompt(msg, { value = "", placeholder = "", okText } = {}) {
  return new Promise((resolve) => {
    _settle = (v) => resolve(typeof v === "string" ? v : null);
    open({ msg, input: { value, placeholder }, okText });
  });
}
