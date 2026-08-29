/* i18n.js — 中英双语文案表（轻量方案：静态界面走 data-i18n，动态消息暂以中文为主） */
const I18N = {
  "nav.create": ["创作", "Create"],
  "nav.gallery": ["画廊", "Gallery"],
  "nav.editor": ["工作流", "Workflows"],
  "nav.runs": ["任务", "Jobs"],
  "nav.launcher": ["启动器", "Launcher"],
  "nav.obsidian": ["知识库", "Vault"],
  "nav.agent": ["助手", "Assistant"],
  "nav.settings": ["设置", "Settings"],
  "nav.about": ["关于", "About"],

  "create.sub": ["本地 ComfyUI · 生成全程在你的显卡上进行", "Local ComfyUI · everything renders on your GPU"],
  "create.mode.image": ["图像生成", "Image"],
  "create.mode.video": ["视频生成", "Video"],
  "create.style": ["风格 SOP", "Style SOP"],
  "create.translate": ["✦ 中文→英文", "✦ ZH→EN"],
  "common.workflow": ["工作流", "Workflow"],
  "common.size": ["尺寸", "Size"],
  "common.count": ["数量", "Count"],
  "common.seed": ["种子", "Seed"],
  "create.go": ["✦ 生 成", "✦ Generate"],
  "create.ph": ["描述你想要的画面…中文会自动转成英文提示词（Flux/H3 对英文跟随更准）",
    "Describe your shot… Chinese is auto-enhanced into English prompts (Flux/H3 follow English better)"],
  "common.inspire": ["灵感", "Inspiration"],
  "create.feed": ["最新创作", "Latest creations"],
  "create.feed.more": ["进入画廊 →", "Open gallery →"],
  "create.hint.image": ["Flux 文生图 · 20步 · 约1-2分钟/张（视队列而定）", "Flux t2i · 20 steps · ~1-2 min per image (queue dependent)"],
  "create.hint.video": ["H3 W4A8 快线 · 640×352 · ≈5秒 · 4步 · 原生音频 · 约8.5分钟/条（视频尺寸由工作流锁定）",
    "H3 W4A8 fast lane · 640×352 · ~5s · 4 steps · native audio · ~8.5 min per clip (size locked by workflow)"],

  "gallery.title": ["画廊", "Gallery"],
  "common.search": ["搜索文件名…", "Search files…"],
  "gallery.all": ["全部", "All"],
  "gallery.video": ["视频", "Videos"],
  "gallery.image": ["图片", "Images"],
  "gallery.sort.new": ["最新优先", "Newest first"],
  "gallery.sort.old": ["最早优先", "Oldest first"],
  "gallery.sort.big": ["文件最大", "Largest first"],
  "gallery.empty": ["还没有成果物。去创作页生成第一个，或让助手「画：xxx」。", "No outputs yet. Create one, or ask the assistant."],

  "editor.title": ["工作流", "Workflows"],
  "editor.name.ph": ["工作流名称", "Workflow name"],
  "editor.save": ["保存", "Save"],
  "editor.run": ["▶ 运行", "▶ Run"],
  "editor.import": ["导入", "Import"],
  "editor.export": ["导出API", "Export API"],
  "editor.new": ["＋ 新建工作流", "＋ New workflow"],
  "editor.hint": ["双击空白添加节点 · 拖动输出口到输入口连线 · 点击已连输入口断开 · Delete 删除选中",
    "Double-click to add nodes · drag out-port to in-port to link · click a linked in-port to unlink · Del removes"],

  "runs.title": ["任务", "Jobs"],
  "runs.interrupt": ["⏹ 中断当前", "⏹ Interrupt"],
  "runs.clear": ["🧹 清空队列", "🧹 Clear queue"],
  "runs.pending": ["排队中", "Queued"],
  "runs.running": ["执行中", "Running"],
  "runs.done": ["最近完成", "Recent"],

  "launcher.title": ["启动器", "Launcher"],
  "launcher.start": ["▶ 启动 ComfyUI", "▶ Start ComfyUI"],
  "launcher.restart": ["↻ 重启", "↻ Restart"],
  "launcher.stop": ["⏹ 停止", "⏹ Stop"],
  "launcher.cfg": ["启动配置", "Launch config"],
  "launcher.dir": ["ComfyUI 目录", "ComfyUI folder"],
  "launcher.py": ["Python 解释器", "Python interpreter"],
  "launcher.args": ["启动参数（空格分隔，保存后下次启动生效）", "Launch args (space separated, saved for next start)"],
  "launcher.save": ["保存配置", "Save config"],
  "launcher.diag": ["环境诊断", "Diagnostics"],
  "launcher.log": ["ComfyUI 日志", "ComfyUI log"],
  "launcher.models": ["模型管理", "Models"],
  "launcher.nodes": ["自定义节点", "Custom nodes"],
  "launcher.log.note": ["data/comfy.log（从创作台启动时才开始记录）", "data/comfy.log (recorded when started from ComfyAgent)"],

  "obsidian.title": ["知识库", "Vault"],
  "obsidian.sync": ["同步工作流到知识库", "Sync workflows to vault"],
  "common.refresh": ["↻ 刷新", "↻ Refresh"],
  "obsidian.archives": ["归档记录", "Archive history"],
  "obsidian.notes": ["知识库笔记", "Vault notes"],

  "agent.title": ["助手", "Assistant"],
  "agent.ph": ["例如：画：雪夜竹林剑客 832x1216 ／ 跑 H3 文生视频 ×2 ／ 归档最近 10 个",
    "e.g. draw: swordsman in snowy bamboo / run H3 t2v ×2 / archive latest 10"],
  "agent.send": ["发送", "Send"],

  "settings.title": ["设置", "Settings"],
  "settings.comfy": ["ComfyUI 地址", "ComfyUI URL"],
  "settings.output": ["成果目录（output）", "Outputs folder"],
  "settings.vault": ["Obsidian 库路径（vault）", "Obsidian vault path"],
  "settings.port": ["服务端口（重启生效）", "Server port (restart to apply)"],
  "settings.zhipu": ["智谱 API Key（选填，提示词增强/助手）", "Zhipu API Key (optional: prompt enhance / assistant)"],
  "settings.zhipu.model": ["智谱模型", "Zhipu model"],
  "settings.lang": ["界面语言 Language", "Interface language"],
  "settings.save": ["保存设置", "Save settings"],
  "settings.test": ["测试 ComfyUI 连接", "Test ComfyUI connection"],
  "settings.gitee.repo": ["Gitee 仓库（owner/repo，用于检查更新）", "Gitee repo (owner/repo, for update check)"],
  "settings.gitee.token": ["Gitee 私人令牌（私有仓检查更新用，选填）", "Gitee token (for private repos, optional)"],
  "settings.update": ["检查更新", "Check updates"],
  "settings.openrel": ["打开下载页", "Open releases"],
  "settings.log": ["运行日志（最近 200 行）", "App log (last 200 lines)"],

  "lb.import": ["导入编辑器", "Open in editor"],
  "lb.rerun": ["重新生成", "Regenerate"],
  "lb.archive": ["归档到知识库", "Archive to vault"],
  "lb.reveal": ["所在文件夹", "Show in folder"],
  "lb.download": ["下载", "Download"],
  "lb.delete": ["删除", "Delete"],
  "lb.note.ph": ["归档手记（可选）", "Archive note (optional)"],
  "lb.copy": ["复制", "Copy"],
  "lb.expand": ["展开", "Expand"],
  "lb.collapse": ["收起", "Collapse"],

  "batch.archive": ["◈ 批量归档", "◈ Archive"],
  "batch.trash": ["🗑 批量删除", "🗑 Delete"],
  "batch.cancel": ["取消", "Cancel"],

  "cmdk.ph": ["输入命令：跳转页面 / 运行工作流 / 中断 / 清空队列…", "Type a command: navigate / run workflow / interrupt / clear queue…"],

  "hw.vram": ["显存", "VRAM"],
  "hw.util": ["利用率", "UTIL"],
  "hw.temp": ["温度", "TEMP"],
  "hw.ram": ["内存", "RAM"],
  "hw.queue": ["队列", "QUEUE"],

  "wizard.title": ["欢迎使用 ComfyAgent 👋", "Welcome to ComfyAgent 👋"],
  "wizard.sub": ["花 30 秒完成初始设置，随时可在「设置」页修改", "30-second setup. Change anything later in Settings."],
  "wizard.skip": ["稍后再说", "Later"],
  "wizard.done": ["完成并进入创作台", "Finish"],

  "misc.refreshing": ["刷新", "Refresh"],
};

let lang = localStorage.getItem("comfyagent_lang") || "zh";

export function t(key) {
  const e = I18N[key];
  if (!e) return key;
  return lang === "en" ? e[1] : e[0];
}
export function getLang() { return lang; }
export function setLang(l) {
  lang = l;
  localStorage.setItem("comfyagent_lang", l);
  applyI18n();
}
export function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
}
