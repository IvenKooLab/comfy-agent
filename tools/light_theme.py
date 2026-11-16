# -*- coding: utf-8 -*-
"""style.css 暗色 -> 苹果亮色主题批量映射（token + 硬编码清扫）"""
import io, re

p = r"E:/work/gitee/comfy-agent/static/style.css"
s = io.open(p, encoding="utf-8").read()

# ===== 1) :root 令牌整段替换 =====
old_root_start = s.index(":root {")
old_root_end = s.index("}", old_root_start) + 1
new_root = """:root {
  /* 亮色主题 — Apple 风格：白底 · 浅灰面板 · 苹果蓝 · 大圆角 · 柔和投影 */
  --bg-0: #f5f5f7;
  --bg-1: #ffffff;
  --bg-2: #ffffff;
  --bg-3: #f5f5f7;
  --bg-4: #e8e8ed;
  --line-1: rgba(0, 0, 0, .07);
  --line-2: rgba(0, 0, 0, .13);
  --text-1: #1d1d1f;
  --text-2: #494950;
  --text-3: #86868b;
  --text-4: #b9bcc4;
  --brand: #0071e3;
  --brand-2: #32ade6;
  --brand-soft: rgba(0, 113, 227, .09);
  --grad: linear-gradient(120deg, #0a84ff 0%, #0071e3 100%);
  --grad-soft: linear-gradient(120deg, rgba(10, 132, 255, .10), rgba(0, 113, 227, .06));
  --ok: #34c759; --warn: #ff9f0a; --err: #ff3b30; --info: #007aff;
  --r-xs: 6px; --r-sm: 9px; --r-md: 12px; --r-lg: 16px; --r-xl: 20px;
  --shadow-1: 0 1px 3px rgba(0, 0, 0, .06);
  --shadow-2: 0 4px 16px rgba(0, 0, 0, .08);
  --shadow-3: 0 12px 40px rgba(0, 0, 0, .12);
  --ease: cubic-bezier(.2, .7, .3, 1);
  --dur: .18s;
  --dur-1: .12s; --dur-2: .2s; --dur-3: .32s;
  --ease-out: cubic-bezier(.22, .61, .36, 1);
  --ease-spring: cubic-bezier(.34, 1.56, .64, 1);
  --font: "MiSans", "PingFang SC", "SF Pro Text", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", "SF Mono", "Cascadia Code", Consolas, monospace;
  --font-list: [D] 20/28, [T1] 16/24, [T2] 14/22, [B] 13/20, [C] 12/18, [X] 11/16;
}"""
s = s[:old_root_start] + new_root + s[old_root_end:]

# ===== 2) 硬编码批量映射（顺序敏感：先长后短）=====
PAIRS = [
    # --- 品牌紫 -> 苹果蓝 ---
    ("rgba(139, 92, 246, .5)", "rgba(0, 113, 227, .45)"),
    ("rgba(139, 92, 246, .6)", "rgba(0, 113, 227, .55)"),
    ("rgba(139, 92, 246, .45)", "rgba(0, 113, 227, .40)"),
    ("rgba(139, 92, 246, .55)", "rgba(0, 113, 227, .50)"),
    ("rgba(139, 92, 246, .65)", "rgba(0, 113, 227, .60)"),
    ("rgba(139, 92, 246, .35)", "rgba(0, 113, 227, .30)"),
    ("rgba(139,92,246,.5)", "rgba(0, 113, 227, .45)"),
    ("rgba(139,92,246,.9)", "rgba(0, 113, 227, .9)"),
    ("rgba(124, 58, 237, .8)", "rgba(0, 113, 227, .85)"),
    ("rgba(124, 58, 237, .85)", "rgba(0, 113, 227, .9)"),
    ("rgba(124, 58, 237, .75)", "rgba(0, 113, 227, .8)"),
    ("rgba(124, 58, 237, .4)", "rgba(0, 113, 227, .35)"),
    ("rgba(124, 58, 237, .12)", "rgba(0, 113, 227, .10)"),
    ("rgba(124, 92, 246, .14)", "rgba(0, 113, 227, .09)"),
    ("rgba(124, 92, 246, .16)", "rgba(0, 113, 227, .10)"),
    ("rgba(124, 92, 246, .35)", "rgba(0, 113, 227, .30)"),
    ("rgba(124, 92, 246, .45)", "rgba(0, 113, 227, .40)"),
    ("rgba(99, 102, 241, .35)", "rgba(0, 113, 227, .30)"),
    ("rgba(99, 102, 241, .42)", "rgba(0, 113, 227, .38)"),
    ("rgba(99, 102, 241, .3)", "rgba(0, 113, 227, .25)"),
    ("#7c5cf6", "#0071e3"),
    ("#7c3aed", "#0a84ff"),
    ("#6366f1", "#0071e3"),
    ("#a78bfa", "#4da3ff"),
    ("rgba(124, 58, 237, .12)", "rgba(0, 113, 227, .10)"),
    # --- 青色辅助 -> 苹果青 ---
    ("rgba(34, 211, 238, .55)", "rgba(50, 173, 230, .55)"),
    ("rgba(34, 211, 238, .4)", "rgba(50, 173, 230, .38)"),
    ("rgba(34, 211, 238, .3)", "rgba(50, 173, 230, .30)"),
    ("rgba(34, 211, 238, .12)", "rgba(50, 173, 230, .12)"),
    ("rgba(34, 211, 238, .055)", "rgba(50, 173, 230, .06)"),
    ("rgba(34, 211, 238, .07)", "rgba(0, 113, 227, .05)"),
    ("rgba(34,211,238,.55)", "rgba(50, 173, 230, .55)"),
    ("#22d3ee", "#32ade6"),
    ("rgba(34, 211, 238, .10)", "rgba(50, 173, 230, .08)"),
    # --- 暗背景浮层 -> 白/浅 ---
    ("rgba(18, 20, 29, .55)", "rgba(255, 255, 255, .75)"),
    ("rgba(6, 7, 11, .2)", "rgba(245, 245, 247, .5)"),
    ("rgba(18, 20, 29, .72)", "rgba(255, 255, 255, .94)"),
    ("rgba(18, 20, 29, .75)", "rgba(255, 255, 255, .95)"),
    ("rgba(18, 20, 29, .8)", "rgba(255, 255, 255, .96)"),
    ("rgba(20, 22, 32, .78)", "rgba(255, 255, 255, .96)"),
    ("rgba(23, 26, 38, .92)", "rgba(255, 255, 255, .97)"),
    ("rgba(8, 9, 14, .9)", "rgba(255, 255, 255, .98)"),
    ("rgba(6, 7, 11, .72)", "rgba(245, 245, 247, .9)"),
    ("rgba(10, 11, 16, .6)", "rgba(245, 245, 247, .85)"),
    ("rgba(10, 11, 16, .55)", "rgba(245, 245, 247, .8)"),
    ("rgba(10, 11, 16, .7)", "rgba(245, 245, 247, .92)"),
    # --- 遮罩层（保持黑但减淡）---
    ("rgba(4, 5, 8, .8)", "rgba(0, 0, 0, .32)"),
    ("rgba(4, 5, 8, .92)", "rgba(0, 0, 0, .38)"),
    ("rgba(4,5,8,.6)", "rgba(0, 0, 0, .28)"),
    ("rgba(5, 6, 10, .62)", "rgba(0, 0, 0, .32)"),
    ("rgba(5, 6, 10, .68)", "rgba(0, 0, 0, .34)"),
    ("rgba(5, 6, 10, .84)", "rgba(0, 0, 0, .38)"),
    ("rgba(4, 5, 8, .6)", "rgba(0, 0, 0, .3)"),
    # --- 阴影减淡 ---
    ("rgba(0, 0, 0, .35)", "rgba(0, 0, 0, .06)"),
    ("rgba(0, 0, 0, .45)", "rgba(0, 0, 0, .08)"),
    ("rgba(0, 0, 0, .6)", "rgba(0, 0, 0, .12)"),
    ("rgba(0, 0, 0, .5)", "rgba(0, 0, 0, .1)"),
    ("rgba(0, 0, 0, .3)", "rgba(0, 0, 0, .07)"),
    # --- 白系边框/文字 -> 亮色下的暗系 ---
    ("rgba(255, 255, 255, .06)", "rgba(0, 0, 0, .06)"),
    ("rgba(255, 255, 255, .05)", "rgba(0, 0, 0, .05)"),
    ("rgba(255, 255, 255, .11)", "rgba(0, 0, 0, .12)"),
    ("rgba(255, 255, 255, .1)", "rgba(0, 0, 0, .08)"),
    ("rgba(255, 255, 255, .18)", "rgba(0, 0, 0, .16)"),
    ("rgba(255, 255, 255, .25)", "rgba(0, 0, 0, .22)"),
    ("rgba(255, 255, 255, .14)", "rgba(0, 0, 0, .14)"),
    ("rgba(255, 255, 255, .16)", "rgba(0, 0, 0, .16)"),
    ("rgba(255,255,255,.55)", "rgba(0, 0, 0, .55)"),
    ("rgba(255, 255, 255, .4)", "rgba(0, 0, 0, .4)"),
    # --- 背景光晕 -> 去花哨，极淡蓝 ---
    ("rgba(124, 58, 237, .12)", "rgba(0, 113, 227, .05)"),
    # --- 深色 hex 点位 ---
    ("#06070b", "#f5f5f7"),
    ("#0c0e15", "#ffffff"),
    ("#12141d", "#ffffff"),
    ("#1a1e2b", "#f5f5f7"),
    ("#232838", "#e8e8ed"),
    ("#14161f", "#f7f7fa"),
    ("#191c2a", "#ffffff"),
    ("#2a1b5e", "#eaf3ff"),
    ("#1a3a5e", "#eaf3ff"),
    ("#0e4a5e", "#e8f4fd"),
    ("#9aa1b5", "#86868b"),
    ("#3a415c", "#d2d5dd"),
    ("#5b6488", "#9aa3b8"),
    ("#4a5478", "#8d97ad"),
    ("#e6e8f0", "#3c3c43"),
    # --- wizard 按钮渐变残留 ---
    ("rgba(124, 58, 237, .16)", "rgba(10, 132, 255, .10)"),
    ("rgba(34, 211, 238, .10)", "rgba(50, 173, 230, .08)"),
    # --- offline banner 保持红系但减淡底 ---
    ("rgba(251, 113, 133, .38)", "rgba(255, 59, 48, .35)"),
    ("rgba(251, 113, 133, .08)", "rgba(255, 59, 48, .07)"),
    ("rgba(251, 113, 133, .85)", "rgba(255, 59, 48, .9)"),
    ("rgba(251, 113, 133, .6)", "rgba(255, 59, 48, .6)"),
    ("rgba(251, 113, 133, .12)", "rgba(255, 59, 48, .12)"),
    # --- draft badge 琥珀适配 ---
    ("rgba(251, 191, 36, .16)", "rgba(255, 159, 10, .14)"),
    ("rgba(251, 191, 36, .35)", "rgba(255, 159, 10, .4)"),
    ("rgba(52, 211, 153, .5)", "rgba(52, 199, 89, .5)"),
    ("rgba(52, 211, 153, .12)", "rgba(52, 199, 89, .12)"),
    ("rgba(52, 211, 153, .18)", "rgba(52, 199, 89, .18)"),
    # --- run state bg ---
    ("rgba(139, 92, 246, .5)", "rgba(0, 113, 227, .45)"),
]
for old, new in PAIRS:
    s = s.replace(old, new)

# ===== 3) body 背景光晕：亮色简约 -> 极淡蓝晕 =====
old_body = """body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background: radial-gradient(1000px 460px at 26% -10%, rgba(0, 113, 227, .05), transparent 62%),
              radial-gradient(860px 400px at 80% -8%, rgba(50, 173, 230, .05), transparent 60%);
}"""
if old_body in s:
    s = s.replace(old_body, """body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background: linear-gradient(180deg, rgba(0, 113, 227, .035), transparent 40%);
}""")

# ===== 4) 残余 #fff 文字：激活态在浅底上要变深（按钮白字保留）=====
# seg-btn.active / nav-item.active / chip.active 等底为浅色的激活态
s = s.replace(".nav-item.active { color: #fff;", ".nav-item.active { color: var(--text-1);")
s = s.replace(".chip.active { background: var(--brand-soft); border-color: rgba(0, 113, 227, .55); color: #fff; }",
              ".chip.active { background: var(--brand-soft); border-color: rgba(0, 113, 227, .55); color: var(--text-1); }")
s = s.replace(".seg-btn.active { background: var(--bg-4); color: #fff;", ".seg-btn.active { background: var(--bg-4); color: var(--text-1);")
s = s.replace(".style-chip.active { background: var(--grad-soft); border-color: rgba(0, 113, 227, .6); color: #fff; }",
              ".style-chip.active { background: var(--brand-soft); border-color: rgba(0, 113, 227, .6); color: var(--text-1); }")
s = s.replace(".tpl-group-item.active { background: var(--brand-soft); color: #fff; }",
              ".tpl-group-item.active { background: var(--brand-soft); color: var(--text-1); }")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
left = len(re.findall(r"rgba\(18, 20, 29|rgba\(6, 7, 11|rgba\(139, 92, 246|rgba\(124, 58, 237|#7c5cf6|#22d3ee", s))
print("dark remnants:", left)
