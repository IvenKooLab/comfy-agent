# ComfyAgent · 可视化创作台

对标可灵 AI 创作台控制台的**本地 ComfyUI 可视化管理 Agent**：暗色控制台风格、零第三方依赖（纯 Python 标准库后端 + 原生 JS 前端），专为「本地显卡跑 ComfyUI 的个人创作者」设计。

![tech](https://img.shields.io/badge/python-stdlib%20only-blue) ![ui](https://img.shields.io/badge/UI-%E5%8F%AF%E7%81%B5%E9%A3%8E%E6%A0%BC%E6%9A%97%E8%89%B2%E6%8E%A7%E5%88%B6%E5%8F%B0-7c5cff)

## 功能总览

| 页面 | 能干什么 |
|---|---|
| 🖼️ **画廊** | 实时瀑布流展示 ComfyUI output 全部成果（视频带 ffmpeg 首帧海报、hover 预览播放）；灯箱查看生成参数（自动解析 PNG 内嵌工作流：模型/采样器/步数/种子/提示词）；一键重跑 / 导入编辑器 / 归档 / 删除（进回收站） |
| 🧩 **工作流** | SVG 节点图可视化编辑器：拖拽节点、连线/断开、缩放平移、双击添加节点（全节点目录搜索）；右侧检查器编辑参数（seed 带🎲随机）；导入 ComfyUI 导出的 UI 格式 JSON（自动转 API 格式）/ API 格式 JSON / **直接拖 PNG 提取内嵌工作流**；内置 Flux 文生图模板 |
| ⚙️ **任务** | 队列状态（执行中/排队中）、WebSocket 实时采样进度条、最近 25 条执行历史带成品缩略图 |
| 🟣 **知识库** | 连接 Obsidian：单图/批量归档（复制媒体 + 生成带元数据的 Markdown 笔记，obsidian:// 一键打开）；工作流单向同步为库内 Markdown 文档 |
| ✨ **助手** | 中文指令直达：「画：雪夜剑客 832x1216」「跑 Flux 文生图 ×3」「归档最近 10 个」「状态/中断/清空队列」；可选配智谱 GLM Key 处理自由表述 |
| 🔧 **设置** | ComfyUI 地址 / output 目录 / Obsidian 库路径 / 端口 / 智谱 Key |

## 快速开始

```bash
# 双击 start.bat，或：
python server.py
# 打开 http://127.0.0.1:8190
```

要求：
- Python 3.9+（无需 pip 装任何东西）
- 本机 ComfyUI（默认 `http://127.0.0.1:8188`，离线时画廊可浏览、编辑器降级可用）
- ffmpeg 在 PATH（视频海报帧缩略图；没有也能跑，只是视频卡片无预览图）
- Obsidian（可选，配置库路径后启用归档）

## 架构

```
comfy-agent/
├── server.py            # 全部后端：静态托管 + REST API + SSE + WS客户端(~1100行, stdlib only)
├── static/
│   ├── index.html       # 单页应用骨架
│   ├── style.css        # 可灵风暗色主题
│   └── js/
│       ├── app.js       # 路由 / API封装 / SSE / Toast
│       ├── gallery.js   # 画廊瀑布流 + 灯箱 + PNG元数据展示
│       ├── editor.js    # SVG 节点图编辑器（连线/检查器/导入导出/节点面板）
│       ├── runs.js      # 队列 + 进度 + 历史
│       └── misc.js      # Obsidian / 助手 / 设置
├── data/                # 运行时数据（设置、工作流库、缩略图缓存、回收站、任务记录）
└── start.bat
```

**通信链路**：浏览器 ⇄ server.py（REST + SSE）⇄ ComfyUI（HTTP API + WebSocket 进度事件）。
进度通过标准库手写的 WebSocket 客户端接收，经 SSE 转发给所有打开的页面；ComfyUI 掉线自动重连。

**工作流格式**：编辑器直接编辑 ComfyUI **API 格式**（即 PNG 内嵌的 `prompt`，与官方 `/prompt` 端点一致）。
导入 UI 格式（前端导出的带 nodes/links 的 JSON）时按 object_info schema 启发式转换 widgets_values，复杂自定义节点可能有警告提示。

## 常用操作速查

- **把 ComfyUI 里调好的工作流搬进来**：ComfyUI 画布 → 导出（API）→ 编辑器「导入」选 JSON → 保存
- **复用某张成图的参数**：画廊点开该图 → 「导入编辑器」或「重新生成」（改 seed）
- **批量跑**：工作流页「运行」输入次数（每批自动换随机 seed），或对助手说「跑 xxx ×5」
- **归档成果**：画廊灯箱点「归档」（可写手记），或对助手说「归档最近 10 个」

## 已知边界

- UI→API 转换是启发式的：标准节点（KSampler/CLIPTextEncode/LoadImage/保存类）验证可靠，冷门自定义节点的控件顺序可能错位（导入后有警告，检查一下参数再跑）
- 视频文件本身不含生成参数，重跑仅对 PNG（ComfyUI 保存时内嵌工作流）有效
- 删除走 `data/trash/` 软删除，不直接抹文件

## License

MIT — 自用顺手就行的私房工具。
