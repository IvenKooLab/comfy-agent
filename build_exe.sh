#!/bin/bash
# ComfyAgent exe 构建脚本（用 ComfyUI 内置 Python，需先: pip install pyinstaller）
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

# 2) 打包（onedir：启动快、误报率低）
"$PY" -m PyInstaller --noconfirm --clean \
  --name ComfyAgent --icon build_assets/icon.ico \
  --add-data "static;static" \
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data \
  server.py

# 3) 发布 zip
cd dist
rm -f ComfyAgent-win64.zip
powershell -NoProfile -Command "Compress-Archive -Path ComfyAgent -DestinationPath ComfyAgent-win64.zip -Force"
cd ..
echo "== DONE: dist/ComfyAgent/ComfyAgent.exe  +  dist/ComfyAgent-win64.zip =="
