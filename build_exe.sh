#!/bin/bash
# ComfyAgent 产品版构建：桌面壳 exe（WebView2 原生窗口 + 托盘，无控制台）
set -e
cd "$(dirname "$0")"
PY="D:/tools/ComfyUI-aki-v3/python/python.exe"

# 1) 图标（无则生成）
if [ ! -f build_assets/icon.ico ]; then
  mkdir -p build_assets
  ffmpeg -v error -y -f lavfi -i "gradients=s=256x256:c0=0x8B5CF6:c1=0x22D3EE" \
    -vf "drawtext=fontfile='C\:/Windows/Fonts/arialbd.ttf':text='C':fontcolor=white:fontsize=155:x=(w-text_w)/2:y=(h-text_h)/2-10" \
    -frames:v 1 build_assets/icon.png
  ffmpeg -v error -y -i build_assets/icon.png build_assets/icon.ico
fi

# 2) 打包（onedir + noconsole 桌面应用）
"$PY" -m PyInstaller --noconfirm --clean \
  --name ComfyAgent --icon build_assets/icon.ico --noconsole \
  --add-data "static;static" \
  --collect-all webview --collect-data pystray \
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data \
  app.py

# 3) 附带运行资源（内置工作流库/版本号）+ 发布 zip
mkdir -p dist/ComfyAgent/data/workflows
cp -f data/workflows/*.json dist/ComfyAgent/data/workflows/ 2>/dev/null || true
cp -f VERSION dist/ComfyAgent/VERSION 2>/dev/null || true
cd dist
rm -f ComfyAgent-win64.zip
powershell -NoProfile -Command "Compress-Archive -Path ComfyAgent -DestinationPath ComfyAgent-win64.zip -Force"
cd ..
echo "== DONE: dist/ComfyAgent/ComfyAgent.exe (desktop app) + dist/ComfyAgent-win64.zip =="
