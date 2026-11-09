#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键重拍 README 截图（Windows / 零第三方依赖）。

用系统自带的 Edge（或 Chrome）无头模式给每个页面截图，再用 ffmpeg 压成 720px 宽的 jpg 缩略图，
写入 docs/screenshot-<view>.png 与 docs/thumbs/screenshot-<view>.jpg（就是 README 里引用的那批图）。

用法（在仓库根目录）：
    python tools/capture_shots.py                # 全部重拍
    python tools/capture_shots.py --only pipeline,create,models
    python tools/capture_shots.py --browser "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

说明：
- 不会碰你本机的 data/ 与 settings.json：脚本在临时目录里跑一个独立实例（含演示批次与占位图）。
- setup wizard 截图不在自动化范围内（它只在全新 localStorage 下出现），保留旧图。
- 需要 Edge/Chrome（Windows 自带 Edge 即可）；缩略图需要 ffmpeg，没有则只更新 png 并给出提示。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

VIEWS = ["create", "templates", "pipeline", "launcher", "models",
         "obsidian", "agent", "help", "settings", "about"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8791

DEMO_SHOTS = [
    ("S01", "开场·山门", "【画风】明亮午后硬光，国漫 3D\n【镜头】整段 4 秒，大全景，平视，缓慢推近\n"
                        "【构图与配色】山门在画面左侧，人物偏右 62% 处\n【人物】白衣少年，背负长剑\n"
                        "【逐秒】0–0.2 秒静止，与首帧一致。少年拾级而上，衣角被风吹起。最后 0.3 秒停住\n"
                        "【声音】只有山风声。人物不说话\n【约束】画面里只有少年与山门，一镜到底，无文字", 4, "establishing"),
    ("S02", "对白·自报家门", "【画风】同上\n【镜头】整段 4 秒，近景，平视，不推不拉\n"
                            "【构图与配色】少年居中偏左，背景虚化的山门\n【人物】白衣少年\n"
                            "【逐秒】0–0.2 秒静止。少年抬头，缓缓开口说：「其实，我是诗仙。」最后 0.3 秒停住\n"
                            "【声音】只有人声与远处鸟鸣\n【约束】画面里只有少年一人，无字幕", 4, "dialogue"),
    ("S03", "反应·众人一愣", "【画风】同上\n【镜头】整段 3 秒，全景，平视，固定机位\n"
                            "【构图与配色】三名书生前中后错落站位\n【人物】三名书生，青衫\n"
                            "【逐秒】0–0.2 秒静止。三人先后面露错愕，随后哄笑，动作有先后。最后 0.3 秒停住\n"
                            "【声音】只有笑声\n【约束】三人不同时做同一动作，无文字", 3, "reaction"),
    ("S04", "对白·出言嘲讽", "【画风】同上\n【镜头】整段 4 秒，近景，过肩，轻微手持\n"
                            "【构图与配色】李秀才在画面右侧 38% 处\n【人物】李秀才，灰袍，留须\n"
                            "【逐秒】0–0.2 秒静止。李秀才眯眼，慢慢捋须说：「还诗仙呢？无知者无畏。」最后 0.3 秒停住\n"
                            "【声音】只有人声\n【约束】画面里只有李秀才，无文字", 4, "dialogue"),
    ("S05", "特写·不动声色", "【画风】同上\n【镜头】整段 3 秒，脸部特写，平视，缓慢推近\n"
                            "【构图与配色】眼睛落在 62% 线附近\n【人物】白衣少年\n"
                            "【逐秒】0–0.2 秒静止。少年眼神平静，嘴角极轻地动了一下。最后 0.3 秒停住\n"
                            "【声音】只有环境底噪，人物不说话\n【约束】画面里只有少年的脸，无文字", 3, "reaction"),
]


def find_browser(explicit=None):
    cands = [explicit] if explicit else []
    cands += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("chromium"), shutil.which("google-chrome"), shutil.which("msedge"),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def build_instance(tmp):
    """临时实例：复制 server.py/static/VERSION + 演示批次 + 占位图，绝不碰本机 data。"""
    for item in ("server.py", "VERSION"):
        shutil.copy2(os.path.join(ROOT, item), os.path.join(tmp, item))
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(tmp, "static"))
    data = os.path.join(tmp, "data")
    os.makedirs(os.path.join(data, "workflows"), exist_ok=True)
    os.makedirs(os.path.join(data, "batches"), exist_ok=True)
    os.makedirs(os.path.join(data, "characters"), exist_ok=True)
    src_wf = os.path.join(ROOT, "data", "workflows")
    if os.path.isdir(src_wf):
        for fn in os.listdir(src_wf):
            if fn.endswith(".json") and ".bak" not in fn and ".crashed." not in fn:
                shutil.copy2(os.path.join(src_wf, fn), os.path.join(data, "workflows", fn))

    out_dir = os.path.join(tmp, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:  # 画廊/创作页有内容可看，避免空态截图
        for i in range(1, 7):
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi",
                            "-i", f"gradients=s=832x1216:c0=0x1b2430:c1=0x6f8fbf:duration=1",
                            "-frames:v", "1", os.path.join(out_dir, f"demo_{i:02d}.png")],
                           capture_output=True, timeout=60)

    items = [{"name": n, "prompt": p, "gen_secs": g, "kind": k,
              "status": "success" if idx < 3 else None} for idx, (n, _, p, g, k) in enumerate(DEMO_SHOTS)]
    batch = {"id": "demo-shortdrama", "name": "E01 诗仙（演示）", "workflow_id": "h3-i2v",
             "aspect": "9:16", "created": "2026-11-09 10:00", "updated": "2026-11-09 10:30",
             "items": items, "palette": {"bg": "#1b2430", "subject": "#e8dfd2",
                                         "accent": "#c8553d", "light": "#f0d9a8"}}
    with open(os.path.join(data, "batches", "demo-shortdrama.json"), "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    with open(os.path.join(data, "characters", "yangyang.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "yangyang", "name": "羊羊", "lock": "白衣少年，黑色长发束起，背负长剑",
                   "lora": "", "lora_strength": 0.8}, f, ensure_ascii=False, indent=2)

    settings = {"port": PORT, "comfy_url": "http://127.0.0.1:8188", "output_dir": out_dir,
                "vault_path": os.path.join(tmp, "vault"), "llm_provider": "zhipu",
                "llm_model": "glm-4-flash", "client_id": "shots"}
    with open(os.path.join(data, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return out_dir


def wait_up(url, timeout=40):
    for _ in range(int(timeout / 0.4)):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def capture(browser, tmp, view, png_path, budget=5000):
    profile = os.path.join(tmp, "profile-" + view)
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=1", "--window-size=1600,1000",
           f"--user-data-dir={profile}", f"--virtual-time-budget={budget}",
           f"--screenshot={png_path}", f"http://127.0.0.1:{PORT}/#{view}"]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    return os.path.isfile(png_path) and os.path.getsize(png_path) > 2000


def to_thumb(png, jpg):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    r = subprocess.run([ffmpeg, "-v", "error", "-i", png, "-vf", "scale=720:-2", "-q:v", "5", "-y", jpg],
                       capture_output=True, timeout=120)
    return os.path.isfile(jpg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的页面名，如 pipeline,create")
    ap.add_argument("--browser", default=None, help="浏览器可执行文件路径（默认自动探测 Edge/Chrome）")
    ap.add_argument("--keep", action="store_true", help="保留临时目录（排错用）")
    args = ap.parse_args()

    browser = find_browser(args.browser)
    if not browser:
        print("找不到 Edge/Chrome。用 --browser 指定路径，或装一个 Chromium 内核浏览器。")
        return 2
    views = [v.strip() for v in args.only.split(",") if v.strip()] or VIEWS
    bad = [v for v in views if v not in VIEWS]
    if bad:
        print("未知页面:", bad, "| 可选:", VIEWS)
        return 2

    tmp = tempfile.mkdtemp(prefix="comfyagent-shots-")
    out_dir = build_instance(tmp)
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=tmp,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok_all = True
    try:
        if not wait_up(f"http://127.0.0.1:{PORT}"):
            print("临时实例没起来（端口被占？改脚本里的 PORT）")
            return 1
        print("浏览器:", browser)
        for v in views:
            png = os.path.join(ROOT, "docs", f"screenshot-{v}.png")
            jpg = os.path.join(ROOT, "docs", "thumbs", f"screenshot-{v}.jpg")
            if capture(browser, tmp, v, png):
                thumb = to_thumb(png, jpg)
                print(f"  {v:10s} png ✓{'  thumb ✓' if thumb else '  thumb ✗(缺 ffmpeg)'}")
            else:
                ok_all = False
                print(f"  {v:10s} 失败")
        print("\n完成。检查 git diff 后提交 docs/ 即可。演示实例的数据在", out_dir)
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
