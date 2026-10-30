# Changelog

## v1.6.0（2026-10-30）— 十月生态同步：MOSS-Image / FLUX 3 Klein 双新生图线

> 距 v1.5.5 六周，ComfyUI 与开源生态密集更新：v0.42.0（10-18）原生支持 MOSS-Image，v0.43.0（10-27）给 MiniMax H3 加单头 LoRA（PDD head banks），10-15 FLUX 3 Image Klein 开源（5.6B）。本次把两条新开源生图线产品化进 ComfyAgent。

- **MOSS-Image 文生图（内置）**（OpenMOSS · Apache-2.0）：按官方模板（image_moss_image_t2i）还原——SFT int8 主模型 + qwen3.5-9b w4a8 编码器（CLIPLoader type=moss_image）+ flux2-vae_small；25 步 er_sde / cfg 2.5，`SkipLayerGuidanceDiTSimple` 跳层 22 细节锚定；中英长文本渲染与 JSON 排版控制直击短剧「文字卡点」刚需。需 ComfyUI ≥ 0.42
- **FLUX 3 Klein 文生图（内置）**（Black Forest Labs）：蒸馏 int8 16 步 euler/simple（追求官方质感可在编辑器换 base 权重走 50 步 cfg 3.5）；原生 4K、文字渲染、边界框排版、多参考图编辑——官方模板 image_flux3_klein_t2i / image_edit 经子图展开一键直连。需 ComfyUI ≥ 0.42
- **模型页新增两个套件**：MOSS-Image 三件套 + edit LoRA + 色深控制 LoRA 全部 hf-mirror 一键断点续传（Comfy-Org 仓库无门控）；FLUX 3 Klein 套件如实标注 gated——主模型/编码器需登录 HF 接受 flux-kommunity-license 后手动放入 models 目录（flux2-vae 与 MOSS 仓库逐字节相同，可一键下载）
- **修复（事故级）：text 覆盖污染负向编码**——submit_workflow 的 text 类覆盖此前会写进所有含 text 键的节点，双 CLIPTextEncode 工作流（MOSS 即是）的负向提示词会被正向内容覆盖；现在只写第一个命中的文本节点（正向约定在前）。H3 单文本节点行为不变，回归测试覆盖
- 创作页图像模式工作流下拉自动出现两个新内置；尺寸注入经 EmptyFlux2LatentImage 生效（1024×1024 起，MOSS 支持到 2M 像素、宽高 16 的倍数）；预估提示不再写死「Flux · 20步」——按所选工作流实时显示名称与采样步数，模式切换即刷新
- 帮助页同步（中英各 2 条：新内置工作流说明、模型页套件清单更新）
- 测试可移植性修复：tests/test_models.py / test_upload_media.py 硬编码开发机绝对路径（`E:/work/gitee/...`），任何其他机器上都直接崩——改为从测试文件位置推导仓库根，非 Windows 环境也能跑通集成链路
- 路线图对齐（详见 docs/竞品分析与路线图.md 2026-10-30 节）：NVIDIA VFX 节点（本地视频放大/补帧/SDR→HDR，10-13 发布）列入 AI 放大导出的候选实现；H3 单头 LoRA 等权重公开；ComfyUI 官方 Comfy Agent（10-01 发布）与本项目的命名重叠及 v1 agent host 接入点注记

**升级注意**：两个新内置工作流依赖 ComfyUI ≥ 0.42 的原生节点（`SkipLayerGuidanceDiTSimple` / `EmptyFlux2LatentImage` / `CLIPLoader` 的 flux3·moss_image 类型）；旧版 ComfyUI 会报节点不存在——启动器页「检查更新 → 一键更新」即可。

## v1.5.5（2026-09-16）— UI 大改版：动效系统 + SVG 图标集 + 全站零 emoji

- **动效系统**（对标 transitions.dev 规范）：动效 token 化（--dur-1/2/3 + ease-out/spring），全部 14 处 `transition: all` 清零只动 opacity/transform；三层动效齐备——进入（弹窗/Toast/切页/列表交错入场）、过渡（按钮悬浮上浮 + 按压回缩、卡片提亮）、消失（弹窗缩退/Toast 滑出/灯箱淡出，动画播完再 hidden）；全局 prefers-reduced-motion 无障碍保护
- **SVG 图标集**：自绘 lucide 风格 16px 描边图标 29 枚（内联零依赖）——导航 13 个、模式 Tab、约 25 个按钮、画廊卡片悬浮操作、关闭按钮全部替换；硬指标**全站零 emoji**（12 页 DOM 扫描归零，i18n 66 行值清洗 + 服务端风格名数据源一并清理）；⚡草稿徽章改样式化 .draft-tag 药丸
- **README 11 张截图全部重摄**（新 UI + 中性演示数据，720px 轻量缩略图 304KB）
- 收录徽章：awesome-alternative-uis-for-comfyui（PR #100 已合并）+ Gitee stars

## v1.5.4（2026-09-16）— 角色 LoRA/ControlNet 位 + 体验修复批

- **角色资产库扩展**：角色卡新增 LoRA 绑定（下拉选择 loras 目录文件 + 强度）与 ControlNet 方案备注（预留位）；创作页选中角色提交生图时自动注入——工作流已有 LoRA 节点则填值，无节点则插入 `LoraLoaderModelOnly` 并重接 MODEL 链
- **画廊批量删除修复（关键）**：确认弹窗关闭时访问未赋值元素抛错吞掉回调，导致所有确认类操作静默失效——根治；另加单文件容错（预览占用不再整批失败）与失败明细提示
- **设置页「打开 ComfyUI 界面」修复**：window.open 被桌面壳/弹窗拦截 → 改后端 ShellExecute 打开（默认浏览器关联损坏时自动探测 Chrome/Edge）
- **i18n**：英文模式工作流列表不再残留中文（WF_EN 补全+对齐新名，编辑器监听 langchange）
- **版本号单一来源**：关于弹窗读 /api/status（VERSION 文件），删除 app.js 硬编码
- 全部 101 条历史提交消息英文化（国际门面）；GitHub Topics 15 个

## v1.5.3（2026-09-10）— 模型管理中心

- **设置页新增「⧉ 打开 ComfyUI 界面」按钮**：一键新开原生 ComfyUI 网页标签（地址跟随设置）
- **新增「模型」页（左侧第 9 菜单，快捷键 9）**：模型不再进 git，改为「清单内置 + 一键下载」——上半部分是推荐套件卡片（首发内置 SCAIL-2 角色动画 6 件套 / MiniMax H3 产线状态展示），逐文件显示安装状态，缺失的点「下载」即走内置 hf-mirror 直连（断点续传 + 实时进度条）；下半部分按目录分类浏览本地 models 文件（checkpoints/diffusion_models/text_encoders/vae/loras/clip_vision 等 10 类），支持搜索、打开文件夹
- **模板缺模型自动检测**：从模板库打开新模板时，后端对照本地模型目录检查 UNETLoader/Checkpoint/VAE/CLIP/LoraLoader 等全部加载节点的引用文件，缺失则弹确认框一键跳转模型页下载——「打开新流程 → 确认下载」闭环
- 帮助页同步最近功能：模型页用法、设置页直达 ComfyUI、编辑器「上传…」按钮、模板缺模型处理（中英各 3 条）
- 新增 API：`/api/models/scan` `/api/models/presets` `/api/models/download` `/api/models/downloads` `/api/models/open_folder`
- 新增 `tests/test_models.py` 集成测试（临时实例 + mock ComfyUI + 假模型目录，4 项断言全绿）

## v1.5.2（2026-09-10）— 子图模板直连（SCAIL-2 就绪）+ 编辑器媒体上传

- **编辑器参数面板支持上传媒体**：LoadImage/LoadVideo/LoadAudio 等文件型参数（COMBO 列表为媒体文件）旁出现「上传…」按钮，图片/视频/音频直接传进 ComfyUI input 目录并自动填入参数——SCAIL-2 的「参考图 + 驱动视频」从此不用离开 ComfyAgent 界面
- 新增 `POST /api/upload_media`（multipart 透传到 ComfyUI /upload/image，上限 1GB）；`api()` 封装支持 FormData
- **模板库支持 ComfyUI subgraph 自动展开**：官方 2026 年 6 月起新模板（SCAIL-2 角色动画/替换、SAM3 分割等）用子图封装，此前一键载入会失败——现在转换器自动展开子图为 API 执行图：输入槽桥接（fan-out 复制）、UUID 链级联解析、widget 绑定线识别、无外部源的数据穿透自动生成 Primitive 节点承载默认值
- 跳过 MarkdownNote 等前端专属节点，不再污染 API 提交图
- 新增 `tests/test_subgraph.py`（5 单测）+ `tests/test_upload_media.py`（透传集成测试）；官方 SCAIL-2 int8 模板（102 节点）离线结构断言全绿
- 用法：模板库搜 "scail" → 载入 → 检查器里直接上传参考图和驱动视频。模型清单见官方模板说明（int8 主模型 15.5G + umt5 6.3G + SAM3 1.6G + VAE/LoRA），fp16 主模型 30G 需 24G+ 显存，16-22G 卡用 int8

## v1.5.1（2026-09-04）— MCP Server 接口 + 看门狗默认关闭

- **MCP Server**（`mcp_server.py`，stdio + JSON-RPC 2.0，零依赖）：外部 Agent/编辑器（ZCode/Claude Desktop/Cursor）可直连本机 ComfyAgent——工具：query_status / submit_generation / list_workflows / search_gallery
- 新增 `POST /api/generate`（生成提交的干净入口，助手工具循环与 MCP 共用）
- **看门狗默认关闭**：用户手动停 ComfyUI（如游戏时段）不再被自动拉起抢 GPU（默认值 + fallback + 存量配置三处关闭）
- bug 修复：「画」正则缺词边界致「画廊里…」误提交生成（事故级）；产线切页 renderBatch 未定义 rejection；命令面板 4 页 undefined 标签 + 搜索必空白

## v1.5.0（2026-09-03）— 助手 Function Calling 工具循环

- **助手接入 function calling**：5 个内置工具——查任务队列 / 搜索画廊 / 读运行日志 / 操作启动器（status·start·stop·restart）/ 提交生成（图片/视频，count≤4）
- **多轮工具循环**（最多 6 轮）：模型自主决定调用哪个工具、读结果、再决定下一步；厂商不支持 tools 协议时自动回落旧意图链路
- **工具过程可见**：助手回复下方以等宽小字逐行展示 🔧 工具名(参数) → 结果摘要
- 工具结果全部摘要化控制 token 体积；生成类工具仅在用户明确要求时触发
- 说明：本版本 Release 暂以源码 tag 发布，exe 安装包待 ComfyUI 空闲窗口打包补挂

## v1.4.3（2026-09-02）— 草稿/成片双档体系

> 把 minimax-h3-turing 研究成果（T8 BlockCache / PDD8 实测数据）产品化为 H3 双档出片流。

- **⚡ 草稿快跑**：产线批次一键用 T8 草稿档快跑全部镜头（t2v 2.7 分钟/镜、i2v 4.3 分钟/镜），挑完镜头后点单镜 ↻ 自动用成片档重跑——两段式出片闭环
- **档位标识**：工作流下拉区分草稿/成片（⚡草稿 徽章），选错档的风险在界面层被拦住
- **动态预估**：创作页预估时长跟随所选工作流显示真实实测值（替掉过时的固定文案），草稿档明确警示「同 seed 不可复现，勿用于成片」
- 服务端注入档位元数据与草稿映射（代码侧，零工作流文件改动）；中英双语；帮助页补两段式用法

## v1.4.2（2026-09-01）— 镜头接龙 + D7 打磨

- **镜头接龙 (↳)**：产线批次里每个镜头可一键「接上一镜尾帧」——自动抽取上一个成功镜头视频的最后一帧，设为本镜 i2v 首帧，一段接一段生成无缝衔接的超长连续镜头
- **优先级排队按钮 (⏫)**：镜头行一键设/取消优先，排队时高优先级镜头先提交（接通后端既有排序）
- **设置卡折叠**：连接与目录 / AI 接入 / 界面与更新 / 可靠性四张卡点击标题收起展开，状态记忆
- **全站 tooltip**：中断/清队列/导出/拼接/灯箱导航等 9 处图标与后果类按钮补悬停说明
- 产线空批次加「新建批次」直达按钮；帮助页同步更新（接龙/优先级用法）
- style.css 重复样式块去重；清理遗留空事件监听

## v1.4.1（2026-08-31）— 界面语言完整化

- **英文模式残留中文清零**：9 个 JS 模块 + index.html 共 300+ 处动态/静态文案全部接入 i18n（toast/确认框/空态/状态条/灯箱参数行/启动器诊断/编辑器检查器等）
- **帮助页双语**：40+ 问答条目全量英文翻译，跟随界面语言即时切换
- **风格 SOP / LLM 厂商 / 内置工作流**显示名客户端本地化（服务端数据保持中文）
- **切换即时生效**：导航/标题/按钮/风格条/工作流下拉/厂商下拉/状态条文字全部监听语言切换事件重渲染
- 修复：画廊「全部」筛选跨语言持久化失配（改为语言中立 sentinel + 旧值自动迁移）；助手历史里持久化的中文欢迎语自动过滤；页面标题跟随语言
- 文案表占位符方案（%s/%n/%m）统一带数字动态文案

## v1.4.0（2026-08-31）— 内置说明书版

- **内置帮助页**：40+ 问答条目覆盖全部 10 个模块，可搜索
- 场景库 / 音频资产 / 字幕烧入 / 风格归纳 / 优先级排队
- exe 体积优化（排除 tkinter/unittest/pydoc_data）

## v1.3.0（2026-08-30）— 产线完善版

- **集数聚合视图**：按批次名前缀聚合统计（镜头数/成功/失败/GPU时间），一键查看每集产能
- **优先级排队**：批次内 priority 镜头优先提交
- **场景库**：场景名+描述+风格令牌 CRUD，同角色库模式
- **音频资产**：自动扫描 output 目录中音频文件（mp3/wav/flac/ogg/aac/m4a）
- **字幕烧入**：ffmpeg srt→video 字幕硬压
- **风格归纳**：多图→GLM 视觉归纳风格关键词→可存为自定义风格 SOP
- **602 官方模板全部真实预览图**（ComfyUI 本地路由代理 + jsdelivr 镜像兜底）
- 修复：循环依赖 TDZ 导致整个界面卡死（$/$$ 改为函数声明）；托盘驻留（关窗后主线程驻留）；模板页骨架屏覆盖容器

## v1.2.0（2026-08-29）— 关键帧锁脸版

- **产线镜头关键帧**：每个镜头可从画廊选一张图作 i2v 首帧——提交时自动复制进 ComfyUI input 目录并注入 LoadImage 源；固定人物图/三视图一键完成
- **画廊选图器**：通用网格选图弹窗（搜索/缩略图预览），产线关键帧与角色参考图共用
- **角色参考图升级**：从手填路径改为画廊选图 + 预览；支持多图（三视图/表情包，最多 4 张）
- **失败自动重试**：批次执行失败自动换种子重试（次数可配）
- **BGM 混音**：拼接成片时可选背景音乐 + 音量调节
- **GPU 耗时账本**：每批自动统计渲染分钟数
- 实测：H3 i2v + 画廊 Flux 图作首帧 → 380 秒出片

## v1.1.0（2026-08-29）— 模板库 + 多厂商 LLM

- **模板库**：ComfyUI 官方 602 模板（9 大分类），搜索/分页/收藏，一键载入编辑器（自动转 API 格式）
- **AI 厂商下拉**：智谱 GLM / DeepSeek / Kimi / 通义千问 / 硅基流动 / OpenAI / 自定义（Base URL 可编辑）
- **模型列表自动拉取**：从厂商 /models 接口获取真实可用模型，失败切手动填写
- **统一 LLM 通道**：提示词增强与助手全部走 OpenAI 兼容协议

## v1.0.0（2026-08-29）— 首个正式版

桌面产品形态 + 全核心功能闭环：

- **桌面壳**：pywebview 原生窗口 + 系统托盘 + 单实例 + 无控制台
- **创作**：中文→英文增强、12 风格 SOP、图/视频双模式、角色锁定串
- **画廊**：实时瀑布流、批量归档/删除、PNG 参数解析、文件夹筛选
- **工作流**：SVG 可视化编辑器（拖拽连线/网格吸附/节点校验）
- **任务**：队列/进度/ETA/失败重试
- **产线**：分集脚本解析→批量排队→逐镜状态→拼接成片
- **角色资产库**：锁定串/参考图
- **启动器**：ComfyUI 启停/版本维护/模型盘点/环境诊断/日志
- **知识库**：Obsidian 归档/统计/双链关系图
- **可靠性三件套**：原子写入、自动备份（保留 20 份）、看门狗（掉线自动重启+断点续跑）
- **多语言**：中英双语界面
- **局域网访问**：手机看进度
- **快捷键**：数字键切页 / Ctrl+K 命令面板 / 搜索

## v0.3.0（2026-08-29）— 内部迭代

- 产品化 UI 重构（设计令牌体系、首次运行向导、关于页）
- 首次运行向导（检测 ComfyUI → 目录 → Obsidian → API Key）

## v0.2.0（2026-08-29）— 内部迭代

- 全站视觉重设计（Composer 首页、画廊悬浮操作、紫青渐变）
- PyInstaller exe 打包

## v0.1.0（2026-08-29）— 初始原型

- 首版：画廊 / 工作流编辑器 / 任务 / Obsidian / 助手 / 设置
