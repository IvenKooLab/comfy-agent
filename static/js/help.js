/* help.js — 内置帮助：全模块使用指南，可搜索（中英双语，跟随界面语言） */
import { $, $$ } from "./app.js";
import { t, getLang } from "./i18n.js";

/* EN 版帮助（结构同 HELP） */
const HELP_EN = [
  { mod: "🚀 Quick start", items: [
    { q: "How do I get started?", a: "1. Make sure ComfyUI is running (bottom-left dot green = online)\n2. Open \"Create\" → pick a style → type a description → Generate\n3. Finished renders appear automatically in the Gallery\n4. First time? Check the ComfyUI URL and output folder in Settings" },
    { q: "What is the bottom status bar?", a: "Real-time GPU status: VRAM / utilization / temperature / RAM / queue.\nAuto-refreshes every 2 seconds. GPU temp ≥83°C turns red as a warning.\n(Source: nvidia-smi)" },
    { q: "Keyboard shortcuts?", a: "Keys 1-8 → switch pages\n/ → focus gallery search\nCtrl+K → command palette (navigate / run workflow / interrupt / clear queue)\nCtrl+S → save workflow (editor)\nCtrl+Enter → run workflow (editor)\nEsc → close dialog / clear selection\nDelete → remove selected node (editor)" },
  ]},
  { mod: "✦ Create", items: [
    { q: "How do I generate an image?", a: "1. Pick a style (e.g. \"Donghua Epic\")\n2. Type a description (e.g. \"a white-robed swordsman looking back above a sea of clouds\")\n3. Choose size and count → Generate\n\nChinese input is auto-translated into an English prompt (Flux follows English better). The translation shows below the input box." },
    { q: "How do I generate a video?", a: "Switch to the \"Video\" tab → pick the H3 workflow → type a description → Generate.\nVideos are fixed at 640×352, ~5s, native audio, ~8.5 min per clip.\nResolution is locked by the workflow (the H3 fast lane has no custom resolution)." },
    { q: "When should I turn off \"ZH→EN\"?", a: "Turn it off when your input is already an English prompt to skip translation.\nEven when off, the English style tokens of the current style SOP are still appended." },
    { q: "What is the \"Character\" dropdown for?", a: "Pick a character from the Character Library; its lock string is appended to the prompt so the character looks consistent across renders.\nCharacters are managed in the Pipeline page's Character Library." },
    { q: "Does count 4 generate 4 different images?", a: "Yes. Each image uses a different random seed, so layout and details vary. Great for exploring before settling on a final." },
  ]},
  { mod: "▦ Gallery", items: [
    { q: "How do I batch delete / archive?", a: "1. Hover a card and a checkbox appears at its top-right; click to select (or Ctrl+click for multi-select)\n2. The batch bar appears at the bottom → \"Archive\" or \"Delete\"\n3. Ctrl+A selects all visible items, Esc clears selection" },
    { q: "What does hovering a card show?", a: "Hovering reveals action buttons (regenerate / open in editor / archive / download / delete).\nVideo cards silently auto-play a preview after 600ms of hover." },
    { q: "What can I do in the lightbox?", a: "Lightbox mode: arrow keys to navigate, Esc to close.\nThe right panel shows generation params (model / sampler / seed / prompt).\nOne-click regenerate, open in editor, or archive to the vault.\nHover a param row to copy it. Click \"Expand\" for long prompts." },
    { q: "How do I filter by folder?", a: "Use the top dropdown (\"All\") → pick a subfolder (e.g. video/, feibi/).\nYour filter choice is remembered." },
    { q: "How does style induction work?", a: "Select a few images with a consistent look → the assistant's vision model induces English style keywords → save them as a custom style SOP.\nGreat for extracting a style from finished shots and reusing it in batch." },
  ]},
  { mod: "❏ Templates", items: [
    { q: "What is the template library?", a: "602 official ComfyUI workflow templates (video / image / audio / 3D / LLM etc., 9 categories) with real example previews.\nClick any template → the workflow is fetched and converted → loaded into the editor → save or run right away." },
    { q: "How does search work?", a: "The top search box fuzzy-matches titles, descriptions and model names.\nFor example, search \"H3\" to find all MiniMax H3 templates." },
    { q: "What are star favorites for?", a: "Starred templates can be quickly found via the \"⭐ Favorites only\" filter. Favorites are stored locally in your browser." },
  ]},
  { mod: "⑃ Workflow editor", items: [
    { q: "How do I add a node?", a: "Double-click empty canvas → a search panel pops up → type the node name → click to add.\nYou can also use the \"＋\" button at the top right." },
    { q: "How do I link / unlink?", a: "Link: drag from a node's right dot to another node's left dot.\nUnlink: click a connected left dot to disconnect.\nWhile dragging you can adjust the path freely." },
    { q: "How do I edit params?", a: "Click a node card → the inspector on the right lists all params → edit in place.\nSeed params have a 🎲 button to randomize.\nRemember to click \"Save\" after editing." },
    { q: "How do I import a ComfyUI workflow?", a: "Export API-format JSON from ComfyUI → click \"Import\" in the editor → pick the JSON file.\nYou can also import a PNG directly (embedded workflow is extracted automatically).\nReview the params, then \"Save\" into the library." },
    { q: "What does a red node border mean?", a: "That node type doesn't exist in the current ComfyUI (a custom-node pack may be missing).\nInstall the matching custom nodes before running." },
  ]},
  { mod: "◷ Jobs", items: [
    { q: "How do I read the progress bar?", a: "The top progress panel shows sampling progress of the current node.\nEach job row also has its own progress bar and ETA." },
    { q: "What if a job fails?", a: "Failed rows show a \"↻ Retry\" button that resubmits with a new seed.\nYou can also batch-retry inside a Pipeline batch." },
    { q: "\"Queued\" vs \"Running\"?", a: "Running = currently rendering on the GPU (has a progress bar).\nQueued = waiting for earlier jobs (FIFO)." },
  ]},
  { mod: "⛓ Pipeline", items: [
    { q: "What is the Pipeline for?", a: "A full assembly line that turns episode scripts into finished videos.\nImport script → parse shot list → edit / set keyframes → queue all → auto-retry → concat into one video." },
    { q: "How do I import a storyboard script?", a: "Click \"Import script\" → paste the full text → \"Parse\".\nIt auto-detects the ### SHOTxx【style】+ text block format.\nA simple one-shot-per-line format also works: name | prompt" },
    { q: "What is a \"keyframe\"?", a: "It assigns an image as the i2v first frame — the video starts from that picture.\nUsed to lock character/scene consistency (far more stable than text).\nPick an image from the gallery; it is copied into ComfyUI's input folder automatically." },
    { q: "How does \"Concat\" work?", a: "Once all shots in a batch succeed, click \"Concat\" to merge them in order into one video file.\nOptionally add BGM (enter an audio path + volume)." },
    { q: "What is the Scene library?", a: "It stores reusable scene descriptions and style tokens for quick reference in new shots.\nLike the Character library, but for scenes/environments instead of people." },
    { q: "What is the Episodes view?", a: "It aggregates batches by name prefix (e.g. E001) into one per-episode stat card: shots / done / failed / GPU time.\nSwitch via \"Episodes\" — handy for managing long series by episode." },
    { q: "How does priority queueing work?", a: "Click ⏫ on a shot row to prioritize it — queued batches submit prioritized shots first.\nUseful for rendering key shots early to check the look before running the rest." },
    { q: "What is Audio assets?", a: "It auto-scans the output folder for audio files (mp3/wav/flac/ogg/aac/m4a) and lists them at the bottom of the Pipeline page.\nPick a BGM path from here when concatenating." },
    { q: "What is the chain button (↳)?", a: "Shot chaining: it auto-extracts the last frame of the previous successful shot and sets it as this shot's i2v first frame.\nUse it to build very long continuous shots that flow seamlessly from one to the next." },
  ]},
  { mod: "⏻ Launcher", items: [
    { q: "What does \"Start ComfyUI\" do?", a: "Starts ComfyUI with your configured args (crash-safe defaults).\nIf ComfyUI is already running you'll be told so.\nAfter startup its log streams below." },
    { q: "What does \"Check updates\" do?", a: "It queries the remote git repo and computes how many commits you're behind.\nIf behind, \"Update\" stashes local changes → pull → restore → prompts you to restart." },
    { q: "What does \"Models\" show?", a: "It scans ComfyUI's models folders: checkpoints/loras/vae/upscale/controlnet, with counts and sizes.\nClick to expand the file list." },
    { q: "How do I change launch args?", a: "Edit the args in the \"Launch config\" card (space separated) and save; applies on next start.\nDefaults are a crash-optimized set (--reserve-vram 2.5 etc.)." },
  ]},
  { mod: "◈ Vault", items: [
    { q: "How do I archive images to Obsidian?", a: "Select images in the gallery → \"Archive\" → a Markdown note is created under ComfyAgent/notes in your vault (with embedded images and a params table).\nBatch archive works the same, merging multiple files into one note." },
    { q: "What is the link graph?", a: "Inspired by Obsidian's graph view — a canvas force-directed map of wiki links between notes in your vault.\nNode size = word count; drag to arrange; double-click a node to open the note." },
    { q: "How does note search work?", a: "Type a keyword in the top search box → matching notes filter live → click to preview the full text (first 8000 chars) → jump into Obsidian to edit." },
  ]},
  { mod: "✧ Assistant", items: [
    { q: "What can the assistant do?", a: "Just talk to it:\n· \"draw: swordsman in a snowy bamboo forest\" → enhance and generate\n· \"run H3 t2v ×2\" → queue a batch\n· \"archive latest 10\" → batch archive\n· \"status / interrupt / clear queue\" → manage jobs\n· \"paint in ink-wash style: xxx\" → applies the style SOP automatically" },
    { q: "Will chat history be lost?", a: "No. Chat history is stored locally in your browser and survives refreshes and restarts." },
  ]},
  { mod: "⚙ Settings", items: [
    { q: "How do I switch AI providers?", a: "Pick a provider (Zhipu / DeepSeek / Kimi / Qwen / SiliconFlow / OpenAI / Custom) → Base URL auto-fills → enter your API key → \"Fetch models\" → pick a model → Save.\nIf fetching fails you can type the model name manually." },
    { q: "What does \"Check updates\" do?", a: "It checks Gitee for newer Releases. Private repos need a Gitee token (stored locally, never sent back to the page)." },
    { q: "Is \"Allow LAN access\" safe?", a: "When on, phones/tablets on the same Wi-Fi can open the console at http://your-ip:8190 — handy for monitoring from a phone.\nNote: everyone on the LAN can access it; use only on trusted networks." },
  ]},
];


const HELP = [
  { mod: "🚀 快速上手", items: [
    { q: "第一次用怎么做？", a: "1. 确认 ComfyUI 已启动（左下角绿点亮 = 在线）\n2. 点左侧「创作」→ 选风格 → 输入中文描述 → 点生成\n3. 生成完成后自动出现在「画廊」\n4. 首次使用请在「设置」检查 ComfyUI 地址和 output 目录" },
    { q: "底部状态条是什么？", a: "显示实时 GPU 状态：显存占用 / 利用率 / 温度 / 内存 / 队列数。\n每 2 秒自动刷新。GPU 温度 ≥83°C 变红警告。\n（数据来源：nvidia-smi）" },
    { q: "快捷键有哪些？", a: "数字键 1-8 → 快速切换页面\n/ → 聚焦画廊搜索\nCtrl+K → 命令面板（跳页/跑工作流/中断/清队列）\nCtrl+S → 保存工作流（编辑器页）\nCtrl+Enter → 运行工作流（编辑器页）\nEsc → 关闭弹窗 / 清除选择\nDelete → 删除选中节点（编辑器页）" },
  ]},
  { mod: "✦ 创作页", items: [
    { q: "怎么生成图片？", a: "1. 选风格（如「国漫史诗」）\n2. 输入中文描述（如「云海之巅的白衣剑客回眸」）\n3. 选尺寸和数量 → 点「生成」\n\n中文会自动翻译成英文提示词（Flux 对英文跟随更好）。翻译结果显示在输入框下方。" },
    { q: "怎么生成视频？", a: "切到「视频生成」Tab → 选 H3 工作流 → 输入描述 → 生成。\n视频固定 640×352、约 5 秒、带原生音频、约 8.5 分钟/条。\n尺寸由工作流锁定（H3 快线不支持自定义分辨率）。" },
    { q: "「中文→英文」开关什么时候关？", a: "如果输入本身就是英文提示词，可以关掉跳过翻译。\n关闭后系统仍会追加当前风格 SOP 的英文风格令牌。" },
    { q: "「角色」下拉是干什么的？", a: "从「角色资产库」选一个角色，其锁定串会自动追加到提示词尾部，保证多次生成角色外观一致。\n角色在「产线」页的角色资产库中管理。" },
    { q: "数量选 4 是生成 4 张不同的图吗？", a: "是的，每张用不同的随机种子，布局和细节各不相同。适合先出多张挑选再定稿。" },
  ]},
  { mod: "▦ 画廊", items: [
    { q: "怎么批量删除/归档？", a: "1. 鼠标悬停图片右上角出现勾选框，点选（或 Ctrl+点击多选）\n2. 底部出现批量操作条 → 点「批量归档」或「批量删除」\n3. Ctrl+A 全选可见项，Esc 取消选择" },
    { q: "悬停图片能看到什么？", a: "图片卡片悬停出现操作按钮（重新生成/导入编辑器/归档/下载/删除）。\n视频卡片悬停 600ms 后自动静默播放预览。" },
    { q: "点开大图后能干什么？", a: "灯箱模式：左右箭头切换、Esc 关闭。\n右侧面板显示生成参数（模型/采样器/种子/提示词）。\n可一键重新生成、导入编辑器、归档到知识库。\n悬停参数行可复制内容。长提示词点「展开」看全文。" },
    { q: "怎么按文件夹筛选？", a: "顶部下拉框「全部」→ 选子目录（如 video/、feibi/）。\n筛选会记住你的选择。" },
    { q: "风格归纳怎么用？", a: "选几张风格统一的图 → 助手用视觉模型归纳出英文风格关键词 → 可保存为自定义风格 SOP。\n适合从满意的成片里反提风格，批量复用。" },
  ]},
  { mod: "❏ 模板库", items: [
    { q: "模板库是什么？", a: "ComfyUI 官方 602 个工作流模板（视频/图像/音频/3D/LLM 等 9 大分类），带真实实例图预览。\n点击任意模板 → 自动拉取工作流并转换 → 载入编辑器 → 保存或直接运行。" },
    { q: "搜索怎么用？", a: "顶栏搜索框支持标题、描述、模型名模糊搜索。\n例如搜「H3」可找到所有 MiniMax H3 模板。" },
    { q: "星标收藏有什么用？", a: "点星标收藏的模板可通过「⭐ 只看收藏」筛选快速找到。收藏存在浏览器本地。" },
  ]},
  { mod: "⑃ 工作流编辑器", items: [
    { q: "怎么添加节点？", a: "双击画布空白处 → 弹出搜索面板 → 输入节点名 → 点击添加。\n也可以点右上角「＋」按钮。" },
    { q: "怎么连线/断线？", a: "连线：从节点右侧圆点拖到另一节点左侧圆点。\n断线：点击已连接的左侧圆点即可断开。\n连线时按住拖动可调整路径。" },
    { q: "怎么编辑参数？", a: "点击节点卡片 → 右侧检查器显示所有参数 → 直接编辑。\n种子参数带🎲按钮可随机化。\n修改后记得点「保存」。" },
    { q: "怎么导入 ComfyUI 的工作流？", a: "在 ComfyUI 导出 API 格式 JSON → 点编辑器「导入」→ 选 JSON 文件。\n也可以直接导入 PNG（自动提取内嵌工作流）。\n导入后检查参数，点「保存」入库。" },
    { q: "节点有红色边框是什么意思？", a: "表示该节点类型在当前 ComfyUI 中不存在（可能缺少自定义节点包）。\n需要安装对应的自定义节点后才能运行。" },
  ]},
  { mod: "◷ 任务页", items: [
    { q: "进度条怎么看？", a: "顶部进度面板显示当前执行节点的采样进度。\n每个任务行也有独立的进度条和预计剩余时间。" },
    { q: "失败了怎么办？", a: "失败任务行有「↻ 重试」按钮，点击自动换种子重新提交。\n也可以在「产线」批次中批量重试。" },
    { q: "「排队中」和「执行中」的区别？", a: "执行中 = 正在 GPU 上渲染（有进度条）。\n排队中 = 等待前面的任务完成（FIFO 先进先出）。" },
  ]},
  { mod: "⛓ 产线", items: [
    { q: "产线是干什么的？", a: "把分集脚本变成成品视频的完整流水线。\n导入脚本 → 解析镜头清单 → 编辑/设关键帧 → 批量排队 → 自动重试 → 拼接成片。" },
    { q: "怎么导入分镜脚本？", a: "点「导入分镜脚本」→ 粘贴脚本全文 → 点「解析」。\n自动识别 ### SHOT编号【画风】+ text 代码块格式。\n也支持每行一段的简单格式：镜头名 | 提示词" },
    { q: "「关键帧」是什么？", a: "给镜头指定一张图作为 i2v 首帧，视频从这个画面开始生成。\n用于固定人物/场景一致性（比文字描述稳定得多）。\n从画廊选图即可，自动复制到 ComfyUI input 目录。" },
    { q: "「拼接成片」怎么用？", a: "批次内所有镜头成功后，点「拼接成片」按顺序合并为一个视频文件。\n可选添加 BGM 背景音乐（输入音频路径 + 音量）。" },
    { q: "场景库是干什么的？", a: "保存常用场景描述和风格令牌。创建新镜头时可以快速引用。\n和角色库类似，但管理的是场景/环境而不是人物。" },
    { q: "集数聚合视图是什么？", a: "按批次名前缀（如 E001）把多个批次聚合成一集的统计卡：镜头数/成功/失败/GPU 时间。\n点「集数视图」切换，适合长剧按集管理产能。" },
    { q: "优先级排队怎么用？", a: "镜头行点 ⏫ 设为优先——批次排队时高优先级镜头先提交。\n适合先把关键镜头跑出来看效果，再补剩余镜头。" },
    { q: "音频资产是什么？", a: "自动扫描 output 目录里的音频文件（mp3/wav/flac/ogg/aac/m4a）列在产线页底部。\n拼接成片选 BGM 时可直接从这里取路径。" },
    { q: "「接尾帧」(↳) 是干什么的？", a: "镜头接龙：自动抽取上一个成功镜头视频的最后一帧，设为当前镜头的 i2v 首帧。\n适合做超长连续镜头：一段接一段，画面无缝衔接。" },
  ]},
  { mod: "⏻ 启动器", items: [
    { q: "「启动 ComfyUI」按钮做什么？", a: "用配置的参数启动 ComfyUI（默认 h3_launch.sh 防炸参数）。\n如果 ComfyUI 已在运行则提示。\n启动后日志实时显示在下方。" },
    { q: "「检查更新」做什么？", a: "从远端 git 仓库拉取最新代码，计算本地落后多少提交。\n如果落后，点「一键更新」自动 stash 本地改动 → pull → 恢复 → 提示重启。" },
    { q: "「模型管理」显示什么？", a: "自动扫描 ComfyUI 的 models 目录：checkpoints/loras/vae/upscale/controlnet，显示数量和体积。\n点击可展开文件列表。" },
    { q: "启动参数怎么改？", a: "「启动配置」卡片中编辑启动参数（空格分隔），保存后下次启动生效。\n默认参数是防炸优化版（--reserve-vram 2.5 等）。" },
  ]},
  { mod: "◈ 知识库", items: [
    { q: "怎么把图片归档到 Obsidian？", a: "画廊中选中图片 → 点「归档到知识库」→ 自动在 Obsidian vault 的 ComfyAgent/notes 下创建 Markdown 笔记（含嵌入图片和参数表格）。\n批量归档同理，多个文件合并为一篇笔记。" },
    { q: "双链关系图是什么？", a: "模仿 Obsidian 的 graph view，用 canvas 力导向图展示 vault 中笔记之间的 wiki 链接关系。\n节点大小 = 字数权重，可拖拽整理布局，双击节点打开笔记。" },
    { q: "笔记搜索怎么用？", a: "顶栏搜索框输入关键词 → 实时过滤匹配的笔记 → 点击预览全文（前 8000 字符）→ 可跳转 Obsidian 编辑。" },
  ]},
  { mod: "✧ 助手", items: [
    { q: "助手能做什么？", a: "用中文说就行：\n· 「画：雪夜竹林剑客」→ 自动增强并生图\n· 「跑 H3 文生视频 ×2」→ 批量排队\n· 「归档最近 10 个」→ 批量归档\n· 「状态 / 中断 / 清空队列」→ 管理\n· 「用国风水墨画：xxx」→ 自动挂载风格 SOP" },
    { q: "对话记录会丢吗？", a: "不会。对话历史存在浏览器本地，刷新或重开都保留。" },
  ]},
  { mod: "⚙ 设置", items: [
    { q: "AI 厂商怎么切换？", a: "下拉选择厂商（智谱/DeepSeek/Kimi/通义/硅基流动/OpenAI/自定义）→ Base URL 自动填充 → 填 API Key → 点「拉取模型」→ 选模型 → 保存。\n如果拉取失败可以手动填模型名。" },
    { q: "「检查更新」做什么？", a: "从 Gitee 检查是否有新版本 Release。私有仓需要配置 Gitee 私人令牌（token 只存本地不回传）。" },
    { q: "「允许局域网访问」安全吗？", a: "开启后同一 WiFi 下的手机/平板可以通过 http://你的IP:8190 访问创作台，方便手机看进度。\n注意：局域网内所有人都能访问，仅在可信网络中使用。" },
  ]},
];

let helpSearch = "";

export function initHelp() {
  const box = $("#help-content");
  if (!box) return;
  renderHelp();
  window.addEventListener("langchange", renderHelp);
  $("#help-search").addEventListener("input", (e) => {
    helpSearch = e.target.value.trim().toLowerCase();
    renderHelp();
  });
}

function renderHelp() {
  const box = $("#help-content");
  if (!box) return;
  const data = (getLang() === "en" && HELP_EN) ? HELP_EN : HELP;
  let html = "";
  for (const section of data) {
    const matched = section.items.filter((i) =>
      !helpSearch || i.q.toLowerCase().includes(helpSearch) || i.a.toLowerCase().includes(helpSearch) || section.mod.toLowerCase().includes(helpSearch)
    );
    if (!matched.length && helpSearch) continue;
    html += `<h3 class="help-mod">${section.mod}</h3>`;
    for (const item of matched) {
      html += `<div class="help-item"><div class="help-q">${item.q}</div><div class="help-a">${item.a.replace(/\n/g, "<br>")}</div></div>`;
    }
  }
  if (helpSearch && !html) html = `<div class="muted" style="padding:20px">${t("empty.help.search")}</div>`;
  box.innerHTML = html;
}
