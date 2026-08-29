@echo off
chcp 65001 >nul
title ComfyAgent - 可视化创作台
cd /d "%~dp0"
"D:\tools\ComfyUI-aki-v3\python\python.exe" server.py
pause
