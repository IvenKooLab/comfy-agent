#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ComfyAgent — 可视化创作控制台后端
纯 Python 标准库实现，零第三方依赖。
功能：ComfyUI 代理/进度转发(SSE)、成果画廊(扫描 output 目录 + PNG 元数据 + 视频缩略图)、
     工作流库 + UI->API 转换、Obsidian 归档、规则式 Agent。
"""
import base64
import hashlib
import json
import mimetypes
import os
import queue as queue_mod
import random
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 打包成 exe（PyInstaller）时：静态资源在 _MEIPASS，数据目录放系统 APPDATA（重建/更新永不触碰用户数据）
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    STATIC_DIR = os.path.join(sys._MEIPASS, "static")
    DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming"), "ComfyAgent", "data")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    DATA_DIR = os.path.join(BASE_DIR, "data")
WORKFLOW_DIR = os.path.join(DATA_DIR, "workflows")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbs")
TRASH_DIR = os.path.join(DATA_DIR, "trash")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
RUNS_FILE = os.path.join(DATA_DIR, "runs.json")
ARCHIVE_LOG = os.path.join(DATA_DIR, "archives.json")

DEFAULT_SETTINGS = {
    "port": 8190,
    "comfy_url": "http://127.0.0.1:8188",
    "output_dir": r"D:\tools\ComfyUI-aki-v3\ComfyUI\output",
    "vault_path": r"E:\work\obsidian\TungwaiKu",
    "zhipu_key": "",
    "zhipu_model": "glm-4-flash",
    "client_id": uuid.uuid4().hex,
    "gallery_cap": 2000,
    "comfy_dir": r"D:\tools\ComfyUI-aki-v3\ComfyUI",
    "comfy_python": r"D:\tools\ComfyUI-aki-v3\python\python.exe",
    "comfy_launch_args": "--listen 127.0.0.1 --port 8188 --reserve-vram 2.5 --vram-headroom 0.5 --disable-pinned-memory",
    "gitee_repo": "IvenKooLab/comfy-agent",
    "gitee_token": "",
    "llm_provider": "zhipu",
    "llm_base_url": "https://open.bigmodel.cn/api/paas/v4",
    "llm_key": "",
    "llm_model": "glm-4-flash",
    "comfy_watchdog": True,
    "comfy_autorequeue": True,
    "batch_auto_retry": 2,
    "lan_access": False,
}

# LLM 厂商预设（OpenAI 兼容协议）；models 为兜底列表，优先用 /models 动态拉取
LLM_PRESETS = {
    "zhipu":       {"name": "智谱 GLM",     "base": "https://open.bigmodel.cn/api/paas/v4",             "models": ["glm-4-flash", "glm-4-plus", "glm-4.5", "glm-4.5-air"]},
    "deepseek":    {"name": "DeepSeek",      "base": "https://api.deepseek.com/v1",                       "models": ["deepseek-chat", "deepseek-reasoner"]},
    "moonshot":    {"name": "月之暗面 Kimi", "base": "https://api.moonshot.cn/v1",                        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"]},
    "dashscope":   {"name": "阿里通义千问",  "base": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": ["qwen-plus", "qwen-turbo", "qwen-max"]},
    "siliconflow": {"name": "硅基流动",      "base": "https://api.siliconflow.cn/v1",                     "models": ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3"]},
    "openai":      {"name": "OpenAI",        "base": "https://api.openai.com/v1",                         "models": ["gpt-4o-mini", "gpt-4o"]},
    "custom":      {"name": "自定义 OpenAI 兼容", "base": "", "models": []},
}

MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
FFMPEG = shutil.which("ffmpeg")

# ---------------------------------------------------------------- utilities

def ensure_dirs():
    for d in (DATA_DIR, WORKFLOW_DIR, CACHE_DIR, THUMB_DIR, os.path.dirname(SETTINGS_FILE)):
        os.makedirs(d, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:
            pass
    # 旧版 zhipu_key/zhipu_model → 新 llm_* 字段迁移
    if not s.get("llm_key") and s.get("zhipu_key"):
        s["llm_provider"] = "zhipu"
        s["llm_key"] = s["zhipu_key"]
        s["llm_model"] = s.get("zhipu_model", "glm-4-flash")
        s["llm_base_url"] = LLM_PRESETS["zhipu"]["base"]
    return s


def write_text_atomic(path, text):
    """原子写文本：先写 .tmp 再 os.replace，断电/崩溃不会留下半截文件。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save_settings(s):
    write_text_atomic(SETTINGS_FILE, json.dumps(s, ensure_ascii=False, indent=2))


def backup_now(reason="manual"):
    """打包核心数据（工作流库/批次/角色/设置/任务记录）到 data/backups，保留最近 20 份。"""
    import zipfile
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(DATA_DIR, "backups")
    os.makedirs(bdir, exist_ok=True)
    dst = os.path.join(bdir, f"backup_{ts}_{reason}.zip")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("workflows", "batches", "characters"):
            root = os.path.join(DATA_DIR, sub)
            if os.path.isdir(root):
                for dp, _, fs in os.walk(root):
                    for f in fs:
                        fp = os.path.join(dp, f)
                        z.write(fp, os.path.relpath(fp, DATA_DIR))
        for f in (SETTINGS_FILE, RUNS_FILE, ARCHIVE_LOG):
            if os.path.isfile(f):
                z.write(f, os.path.relpath(f, DATA_DIR))
    zips = sorted([os.path.join(bdir, f) for f in os.listdir(bdir) if f.startswith("backup_")],
                  key=os.path.getmtime)
    for old in zips[:-20]:
        try:
            os.remove(old)
        except OSError:
            pass
    return {"file": os.path.basename(dst), "count": len(zips[-20:])}


SETTINGS = None  # set in main()


def read_json_file(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_file(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024.0


def kind_of(ext):
    return "video" if ext in VIDEO_EXTS else "image"


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()[:80]


# ---------------------------------------------------------------- ComfyUI client

class ComfyClient:
    """HTTP 客户端 + 便携 WebSocket 客户端（标准库实现）。"""

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.online = False
        self.object_info_cache = None
        self.object_info_ts = 0

    def http(self, path, payload=None, method=None, timeout=10):
        url = self.base + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            try:
                return json.loads(body)
            except Exception:
                return body

    def probe(self):
        try:
            st = self.http("/system_stats", timeout=4)
            self.online = True
            return st
        except Exception:
            self.online = False
            return None

    def object_info(self, max_age=600):
        if self.object_info_cache and time.time() - self.object_info_ts < max_age:
            return self.object_info_cache
        oi = self.http("/object_info", timeout=60)
        self.object_info_cache = oi
        self.object_info_ts = time.time()
        return oi


class MiniWS:
    """够用的 WebSocket 客户端：握手 + 文本帧收发 + ping/pong。"""

    def __init__(self, url):
        self.url = url
        self.sock = None
        self.alive = False

    def connect(self):
        u = urllib.parse.urlparse(self.url)
        host, port = u.hostname, u.port or (443 if u.scheme == "wss" else 80)
        path = u.path + ("?" + u.query if u.query else "")
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(None)
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("ws handshake eof")
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise ConnectionError("ws handshake rejected: " + head[:120].decode("utf-8", "ignore"))
        self.alive = True
        self._leftover = rest

    def _read_exact(self, n):
        data = self._leftover
        self._leftover = b""
        while len(data) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("ws eof")
            data += chunk
        self._leftover = data[n:]
        return data[:n]

    def recv_text(self):
        """阻塞收一帧；返回 (opcode, text-or-None)。二进制帧直接丢弃。"""
        while True:
            hdr = self._read_exact(2)
            fin_op = hdr[0]
            opcode = fin_op & 0x0F
            mask_len = hdr[1]
            masked = bool(mask_len & 0x80)
            length = mask_len & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(length) if length else b""
            if opcode == 0x9:  # ping -> pong
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:  # close
                raise ConnectionError("ws closed by server")
            if opcode in (0x1, 0x2):
                return opcode, payload.decode("utf-8", "replace")
            # pong / 其他：忽略

    def _send_frame(self, opcode, payload=b""):
        mask = os.urandom(4)
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def close(self):
        self.alive = False
        try:
            if self.sock:
                self._send_frame(0x8)
                self.sock.close()
        except Exception:
            pass


COMFY = None  # set in main()

# ---------------------------------------------------------------- SSE hub

class SSEHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.subscribers = []
        self.state = {"comfy_online": False, "queue_remaining": 0, "progress": None,
                      "executing": None, "last_event": None}

    def subscribe(self):
        q = queue_mod.Queue(maxsize=500)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def publish(self, event):
        self.state["last_event"] = event
        if event.get("type") == "status":
            self.state["queue_remaining"] = event.get("data", {}).get("value", self.state["queue_remaining"])
        elif event.get("type") == "progress":
            d = event.get("data", {})
            self.state["progress"] = {"value": d.get("value"), "max": d.get("max"),
                                      "prompt_id": d.get("prompt_id"), "node": d.get("node")}
        elif event.get("type") == "executing":
            d = event.get("data", {})
            if d.get("node") is None:
                self.state["progress"] = None
                self.state["executing"] = None
            else:
                self.state["executing"] = d
        elif event.get("type") in ("execution_success", "execution_error", "execution_interrupted"):
            self.state["progress"] = None
            self.state["executing"] = None
        with self.lock:
            subs = list(self.subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue_mod.Full:
                pass


HUB = SSEHub()


def ws_monitor_loop():
    """维持与 ComfyUI 的 WS 长连，事件转发到 SSE hub。"""
    while True:
        ws_url = COMFY.base.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += "/ws?clientId=" + SETTINGS["client_id"]
        ws = MiniWS(ws_url)
        try:
            ws.connect()
            COMFY.online = True
            HUB.state["comfy_online"] = True
            HUB.publish({"type": "comfy_status", "data": {"online": True}})
            while True:
                opcode, text = ws.recv_text()
                if opcode != 1:
                    continue
                try:
                    msg = json.loads(text)
                except Exception:
                    continue
                if isinstance(msg, dict) and "type" in msg:
                    HUB.publish(msg)
        except Exception:
            pass
        finally:
            ws.close()
            COMFY.online = False
            HUB.state["comfy_online"] = False
            HUB.state["progress"] = None
            HUB.state["executing"] = None
            HUB.publish({"type": "comfy_status", "data": {"online": False}})
        time.sleep(4)


def queue_poll_loop():
    """WS 断开时的兜底：轮询 /queue。"""
    last = None
    while True:
        time.sleep(3)
        if COMFY.online:
            continue
        try:
            q = COMFY.http("/queue", timeout=4)
            running, pending = len(q.get("queue_running", [])), len(q.get("queue_pending", []))
            cur = (running, pending)
            if cur != last:
                last = cur
                HUB.publish({"type": "queue_state", "data": {"running": running, "pending": pending}})
        except Exception:
            pass


# ---------------------------------------------------------------- gallery

_gallery_cache = {"ts": 0, "items": []}
_meta_cache = {}


def scan_gallery(force=False):
    if not force and time.time() - _gallery_cache["ts"] < 4:
        return _gallery_cache["items"]
    root = SETTINGS["output_dir"]
    items = []
    if os.path.isdir(root):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in MEDIA_EXTS and ext not in VIDEO_EXTS:
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, root).replace("\\", "/")
                it = {"path": rel, "name": fn, "kind": kind_of(ext), "ext": ext,
                      "size": st.st_size, "mtime": int(st.st_mtime)}
                if ext == ".png":
                    try:
                        w, h = png_size(full)
                        it["w"], it["h"] = w, h
                    except Exception:
                        pass
                items.append(it)
    items.sort(key=lambda x: x["mtime"], reverse=True)
    items = items[:SETTINGS.get("gallery_cap", 2000)]
    _gallery_cache["ts"] = time.time()
    _gallery_cache["items"] = items
    return items


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None, None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def png_workflow_meta(path):
    """读取 ComfyUI 写入 PNG tEXt 块里的 prompt(API) 与 workflow(UI) 元数据。"""
    key = (path, os.path.getmtime(path) if os.path.exists(path) else 0)
    if key in _meta_cache:
        return _meta_cache[key]
    out = {"prompt": None, "workflow": None}
    try:
        with open(path, "rb") as f:
            data = f.read()
        pos = 8
        while pos + 8 <= len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            ctype = data[pos + 4:pos + 8]
            cdata = data[pos + 8:pos + 8 + length]
            if ctype == b"tEXt":
                null = cdata.find(b"\x00")
                if null > 0:
                    kw = cdata[:null].decode("latin-1")
                    val = cdata[null + 1:].decode("utf-8", "replace")
                    if kw in ("prompt", "workflow"):
                        try:
                            out[kw] = json.loads(val)
                        except Exception:
                            pass
            elif ctype == b"IDAT":
                break
            pos += 12 + length
    except Exception:
        pass
    _meta_cache[key] = out
    return out


def summarize_api_graph(api):
    """把 API 工作流摘要成可读参数（画廊详情/归档用）。"""
    if not isinstance(api, dict):
        return {}
    summary = {"model": None, "sampler": None, "steps": None, "cfg": None, "seed": None,
               "dimensions": None, "prompt": None, "negative": None, "nodes": len(api)}
    for nid, node in api.items():
        ct = node.get("class_type", "")
        ins = node.get("inputs", {}) or {}
        if ct in ("CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader", "VAELoader"):
            for k in ("ckpt_name", "unet_name", "vae_name"):
                if isinstance(ins.get(k), str):
                    summary["model"] = ins[k]
        elif "KSampler" in ct or "Sampler" in ct and "Custom" not in ct:
            for k in ("steps", "cfg", "seed", "sampler_name", "denoise"):
                v = ins.get(k)
                if isinstance(v, (int, float, str)):
                    summary[{"sampler_name": "sampler"}.get(k, k)] = v
        elif ct == "EmptySD3LatentImage" or ct == "EmptyLatentImage":
            summary["dimensions"] = f"{ins.get('width')}x{ins.get('height')}"
        elif ct == "CLIPTextEncode":
            t = ins.get("text")
            if isinstance(t, str):
                if summary["prompt"] is None:
                    summary["prompt"] = t
                elif summary["negative"] is None:
                    summary["negative"] = t
    for k, v in list(summary.items()):
        if isinstance(v, str) and len(v) > 500:
            summary[k] = v[:500] + "…"
    return summary


def thumb_path_for(rel, mtime):
    h = hashlib.md5(f"{rel}|{mtime}".encode()).hexdigest()[:16]
    return os.path.join(THUMB_DIR, h + ".jpg")


def make_video_thumb(src, dst):
    if not FFMPEG:
        return False
    try:
        r = subprocess.run([FFMPEG, "-v", "error", "-ss", "0.5", "-i", src,
                            "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", "-y", dst],
                           capture_output=True, timeout=60, creationflags=0x08000000)
        return r.returncode == 0 and os.path.exists(dst)
    except Exception:
        return False


def make_image_thumb(src, dst):
    if not FFMPEG:
        return False
    try:
        r = subprocess.run([FFMPEG, "-v", "error", "-i", src, "-vf", "scale='min(720,iw)':-2",
                            "-q:v", "4", "-y", dst],
                           capture_output=True, timeout=60, creationflags=0x08000000)
        return r.returncode == 0 and os.path.exists(dst)
    except Exception:
        return False


def resolve_media(rel):
    """把画廊相对路径解析成绝对路径，并防目录穿越。"""
    root = os.path.abspath(SETTINGS["output_dir"])
    full = os.path.abspath(os.path.join(root, rel))
    if not full.lower().startswith(root.lower()):
        return None
    return full


# ---------------------------------------------------------------- workflows store

BUILTIN_WORKFLOWS = {
    "Flux 文生图（内置）": {
        "id": "builtin-flux",
        "name": "Flux 文生图（内置）",
        "builtin": True,
        "updated": "2026-08-29 10:00",
        "api": {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "masterpiece, best quality"}},
            "3": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": 3.5}},
            "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["3", 0],
                                                       "seed": 0, "steps": 20, "cfg": 1.0, "sampler_name": "euler",
                                                       "scheduler": "simple", "denoise": 1.0, "latent_image": ["4", 0]}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "flux"}},
        },
    },
    "冒烟测试 LoadImage→SaveImage（内置）": {
        "id": "builtin-smoke",
        "name": "冒烟测试 LoadImage→SaveImage（内置）",
        "builtin": True,
        "updated": "2026-08-29 10:00",
        "api": {
            "1": {"class_type": "LoadImage", "inputs": {"image": "example.png", "upload": "image"}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "agent_smoke"}},
        },
    },
}


# H3 档位元数据（实测值来自 minimax-h3-turing 研究会话，代码侧注入避免改动工作流 json 文件）
# tier: final=成片（同 seed 可复现） draft=草稿（T8 缓存命中致采样分叉，同 seed 不可复现）
WF_META = {
    "builtin-flux": {"tier": "final", "est_min": 1.5},
    "h3-t2v": {"tier": "final", "est_min": 4.7},
    "h3-i2v": {"tier": "final", "est_min": 7.0},
    "h3-t2v-t8draft": {"tier": "draft", "est_min": 2.7},
    "h3-i2v-t8draft": {"tier": "draft", "est_min": 4.3},
    "h3-t2v-pdd8-t8": {"tier": "draft", "est_min": 3.5},
}
# 草稿快跑映射：成片工作流 → 对应草稿档（PDD8 版需 master+PDD 权重，留手动选择）
DRAFT_MAP = {"h3-t2v": "h3-t2v-t8draft", "h3-i2v": "h3-i2v-t8draft"}


def list_workflows():
    out = list(BUILTIN_WORKFLOWS.values())
    for fn in os.listdir(WORKFLOW_DIR):
        # .crashed. 归档（如 sage 崩溃版 h3_t2v.sage_cuda.crashed.json）只留档不入库——误跑会让 ComfyUI 原生崩溃
        if fn.endswith(".json") and ".crashed." not in fn:
            wf = read_json_file(os.path.join(WORKFLOW_DIR, fn), None)
            if wf:
                out.append(wf)
    out.sort(key=lambda w: (w.get("builtin", False) is False, w.get("name", "")))
    for w in out:
        m = WF_META.get(w.get("id"))
        if m:
            w.update(m)
    return out


def workflow_path(wid):
    return os.path.join(WORKFLOW_DIR, safe_name(wid) + ".json")


# ---------------------------------------------------------------- UI -> API converter

LINK_TYPE_TOKENS = {"MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE", "MASK", "CONTROL_NET",
                    "SAMPLER", "SIGMAS", "NOISE", "GUIDER", "LATENT_KEYFRAME"}


def convert_ui_to_api(ui, object_info):
    """ComfyUI 前端导出的 UI 格式 -> API(prompt) 格式。启发式映射 widgets_values。"""
    if not isinstance(ui, dict) or "nodes" not in ui:
        raise ValueError("不是 ComfyUI UI 格式（缺少 nodes）")
    links = {l[0]: l for l in ui.get("links", [])}
    warnings = []
    api = {}
    for node in ui["nodes"]:
        ntype = node.get("type", "")
        nid = str(node.get("id"))
        schema = (object_info or {}).get(ntype)
        ins_def = {}
        if schema:
            ins_def.update(schema.get("input", {}).get("required", {}) or {})
            ins_def.update(schema.get("input", {}).get("optional", {}) or {})
        api[nid] = {"class_type": ntype, "inputs": {}, "_pos": node.get("pos", [0, 0])}
        # 1) 连线输入
        for inp in node.get("inputs", []) or []:
            lname = inp.get("name")
            lid = inp.get("link")
            if lid is None or lid not in links:
                continue
            l = links[lid]
            api[nid]["inputs"][lname] = [str(l[1]), l[2]]
        # 2) widget 标量输入：按 schema 顺序消费 widgets_values
        wv = list(node.get("widgets_values", []) or [])
        consumed = 0
        for pname, pdef in ins_def.items():
            if pname in api[nid]["inputs"]:
                continue
            if not isinstance(pdef, list) or not pdef:
                continue
            ptype = pdef[0]
            if isinstance(ptype, str) and ptype in LINK_TYPE_TOKENS:
                continue  # 连线类型
            if not wv:
                break
            val = wv.pop(0)
            consumed += 1
            api[nid]["inputs"][pname] = val
            # seed 类 INT 自带 control_after_generate 下拉，多吃一个值
            if ptype == "INT" and re.search(r"seed", pname, re.I) and wv and isinstance(wv[0], str) \
                    and wv[0] in ("fixed", "increment", "decrement", "randomize"):
                wv.pop(0)
        if wv:
            warnings.append(f"节点{nid}({ntype}) 有 {len(wv)} 个未能映射的控件值，请检查参数")
    return api, warnings


# ---------------------------------------------------------------- runs registry

def load_runs():
    return read_json_file(RUNS_FILE, [])


def add_run(run):
    runs = load_runs()
    runs.insert(0, run)
    write_json_file(RUNS_FILE, runs[:300])


def update_run(prompt_id, **kw):
    runs = load_runs()
    for r in runs:
        if r.get("prompt_id") == prompt_id:
            r.update(kw)
            break
    write_json_file(RUNS_FILE, runs[:300])


# ---------------------------------------------------------------- obsidian

def vault_name():
    return os.path.basename(SETTINGS["vault_path"].rstrip("\\/"))


def vault_dirs():
    v = SETTINGS["vault_path"]
    return (os.path.join(v, "ComfyAgent", "attachments"),
            os.path.join(v, "ComfyAgent", "notes"),
            os.path.join(v, "ComfyAgent", "workflows"))


def obsidian_uri(relpath):
    q = urllib.parse.quote
    return f"obsidian://open?vault={q(vault_name())}&file={q(relpath)}"


def obsidian_status():
    v = SETTINGS["vault_path"]
    valid = os.path.isdir(v)
    att, notes, wfs = vault_dirs()
    n_notes = len([f for f in os.listdir(notes) if f.endswith(".md")]) if os.path.isdir(notes) else 0
    n_att = len(os.listdir(att)) if os.path.isdir(att) else 0
    return {"path": v, "valid": valid, "is_vault": os.path.isdir(os.path.join(v, ".obsidian")),
            "name": vault_name(), "notes": n_notes, "attachments": n_att}


def archive_media(paths, title="", note="", tags=None):
    """把 output 里的成果复制进 vault，并生成带元数据的 Markdown 笔记。"""
    att_dir, notes_dir, _ = vault_dirs()
    for d in (att_dir, notes_dir):
        os.makedirs(d, exist_ok=True)
    copied, metas = [], []
    ts = datetime.now()
    for rel in paths:
        full = resolve_media(rel)
        if not full or not os.path.exists(full):
            continue
        base = safe_name(os.path.splitext(os.path.basename(rel))[0])
        target = os.path.join(att_dir, f"{ts:%Y%m%d_%H%M%S}_{base}{os.path.splitext(full)[1]}")
        shutil.copy2(full, target)
        st = os.stat(full)
        meta = {"path": rel, "name": os.path.basename(rel), "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "att": os.path.basename(target)}
        if full.lower().endswith(".png"):
            pm = png_workflow_meta(full)
            if pm.get("prompt"):
                meta["summary"] = summarize_api_graph(pm["prompt"])
        metas.append(meta)
        copied.append(os.path.basename(target))
    if not copied:
        return {"ok": False, "error": "没有可归档的文件"}
    title = safe_name(title or (metas[0]["name"] if metas else "归档")) or "归档"
    fname = f"{ts:%Y%m%d_%H%M%S}_{title}.md"
    lines = ["---", f"created: {ts:%Y-%m-%d %H:%M}", "source: ComfyAgent",
             "tags: [" + ", ".join(["comfyui"] + (tags or [])) + "]", "---", "",
             f"# {title}", ""]
    for m in metas:
        lines.append(f"![[{m['att']}]]")
        lines.append("")
        lines.append("| 属性 | 值 |")
        lines.append("|---|---|")
        lines.append(f"| 原文件 | {m['path']} |")
        lines.append(f"| 大小 | {human_size(m['size'])} |")
        lines.append(f"| 生成时间 | {m['mtime']} |")
        s = m.get("summary") or {}
        if s:
            for k, lab in (("model", "模型"), ("sampler", "采样器"), ("steps", "步数"), ("cfg", "CFG"),
                           ("seed", "种子"), ("dimensions", "尺寸")):
                if s.get(k) is not None:
                    lines.append(f"| {lab} | {s[k]} |")
            if s.get("prompt"):
                lines.append(f"| 提示词 | {str(s['prompt']).replace('|', '\\|')[:300]} |")
        lines.append("")
    if note:
        lines += ["## 手记", "", note, ""]
    lines.append(f"*归档自 ComfyUI output · {ts:%Y-%m-%d %H:%M}*")
    rel_note = os.path.relpath(os.path.join(notes_dir, fname), SETTINGS["vault_path"]).replace("\\", "/")
    with open(os.path.join(notes_dir, fname), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log = read_json_file(ARCHIVE_LOG, [])
    log.insert(0, {"note": rel_note, "title": title, "count": len(copied), "time": f"{ts:%Y-%m-%d %H:%M}",
                   "files": copied[:20], "uri": obsidian_uri(rel_note)})
    write_json_file(ARCHIVE_LOG, log[:100])
    return {"ok": True, "note": rel_note, "uri": obsidian_uri(rel_note), "count": len(copied)}


def sync_workflows_to_vault():
    _, _, wf_dir = vault_dirs()
    os.makedirs(wf_dir, exist_ok=True)
    synced = []
    for wf in list_workflows():
        name = wf.get("name", "workflow")
        md = ["---", f"name: {name}", "source: ComfyAgent 工作流同步",
              f"updated: {wf.get('updated', '')}", "tags: [comfyui, workflow]", "---", "", f"# {name}", "",
              "```json", json.dumps(wf.get("api", {}), ensure_ascii=False, indent=2), "```", ""]
        fn = safe_name(name) + ".md"
        with open(os.path.join(wf_dir, fn), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        synced.append(fn)
    return {"ok": True, "count": len(synced), "dir": "ComfyAgent/workflows"}


# ---------------------------------------------------------------- hardware monitor

_NVIDIA_SMI = shutil.which("nvidia-smi")
_hw_cache = {"ts": 0, "data": None}


def get_hardware():
    """GPU/内存实时状态：nvidia-smi(利用率/温度/显存) + ComfyUI system_stats(内存)。1.5s 缓存。"""
    now = time.time()
    if _hw_cache["data"] and now - _hw_cache["ts"] < 1.5:
        return _hw_cache["data"]
    out = {"gpu": None, "ram": None, "queue": HUB.state.get("queue_remaining") or 0,
           "comfy_online": COMFY.online}
    try:
        st = COMFY.http("/system_stats", timeout=4)
        sysi = st.get("system", {})
        out["ram"] = {"total": sysi.get("ram_total"), "free": sysi.get("ram_free")}
        dev = (st.get("devices") or [{}])[0]
        out["gpu"] = {"name": dev.get("name"), "vram_total": dev.get("vram_total"),
                      "vram_free": dev.get("vram_free"), "util": None, "temp": None, "source": "torch"}
    except Exception:
        pass
    if _NVIDIA_SMI:
        try:
            r = subprocess.run(
                [_NVIDIA_SMI, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, creationflags=0x08000000)
            line = r.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                g = {"name": parts[0], "util": float(parts[1]), "temp": float(parts[2]),
                     "vram_used": float(parts[3]) * 1048576, "vram_total": float(parts[4]) * 1048576,
                     "source": "nvidia-smi"}
                out["gpu"] = g
        except Exception:
            pass
    _hw_cache["ts"] = now
    _hw_cache["data"] = out
    return out


# ---------------------------------------------------------------- style SOPs

# 风格 SOP：每个风格 = GLM 增强方向词(direction) + 令牌块(tokens) + 参数覆盖(params)
QUALITY_TAIL = "masterpiece, best quality, ultra detailed, professional color grading, sharp focus, 8k"
STYLE_SOPS = {
    "guoman_epic": {
        "name": "国漫史诗", "emoji": "⚔️",
        "desc": "《凡人修仙传》式 3D 国漫，仙侠史诗感",
        "direction": "3D Chinese animation (guoman) like epic xianxia donghua: stylized realistic characters, painterly skin and fabric textures, grand immortal-mountains atmosphere",
        "tokens": "guoman 3d animation style, epic xianxia atmosphere, stylized character design, cinematic wide composition, volumetric god rays, ",
    },
    "guofeng_ink": {
        "name": "国风水墨", "emoji": "🖌️",
        "desc": "水墨留白，雾山云海，东方意境",
        "direction": "traditional Chinese ink-wash painting (shui-mo) with generous negative space, misty mountains, subtle color accents on rice paper texture",
        "tokens": "chinese ink wash painting, xieyi brushwork, misty negative space, rice paper texture, muted indigo accents, ",
    },
    "cinematic_film": {
        "name": "电影质感", "emoji": "🎬",
        "desc": "写实电影感，浅景深，专业调色",
        "direction": "cinematic film still: anamorphic lens, shallow depth of field, motivated practical lighting, teal-and-orange professional color grading, filmic grain",
        "tokens": "cinematic film still, anamorphic bokeh, shallow depth of field, dramatic rim lighting, film grain, color graded, ",
    },
    "cyber_neon": {
        "name": "赛博霓虹", "emoji": "🌃",
        "desc": "雨夜霓虹，高对比科幻都市",
        "direction": "cyberpunk aesthetic: rain-soaked neon streets, holographic signage, high contrast cyan-magenta palette, reflective wet surfaces",
        "tokens": "cyberpunk, neon signage glow, rain reflections, cyan and magenta palette, night city haze, ",
    },
    "storybook": {
        "name": "插画绘本", "emoji": "📖",
        "desc": "温暖童书插画，柔和手绘质感",
        "direction": "warm children's storybook illustration: soft hand-painted textures, gentle rounded shapes, cozy narrative mood",
        "tokens": "storybook illustration, soft hand-painted texture, warm pastel palette, cozy whimsical mood, ",
    },
    "ghibli_warm": {
        "name": "温暖手绘", "emoji": "🍃",
        "desc": "吉卜力式自然光手绘，治愈日常",
        "direction": "hand-drawn animation style inspired by studio ghibli: lush painted backgrounds, natural light, gentle nostalgic warmth",
        "tokens": "ghibli inspired hand-drawn style, lush painted background, cumulus clouds, natural soft light, nostalgic warmth, ",
    },
    "thick_paint": {
        "name": "厚涂油画", "emoji": "🎨",
        "desc": "印象派厚涂笔触，颜料质感",
        "direction": "impressionist oil painting with thick impasto brushstrokes, visible palette-knife texture, rich layered colors",
        "tokens": "thick impasto oil painting, visible brushstrokes, palette knife texture, rich layered pigments, ",
    },
    "figure_3d": {
        "name": "3D 手办", "emoji": "🧸",
        "desc": "收藏级手办渲染，棚拍布光",
        "direction": "collectible 3D figure render: glossy anime-style figurine on a display base, studio softbox lighting, product photography",
        "tokens": "3d collectible figure, glossy anime figurine, studio product lighting, display base, octane render, ",
    },
    "chibi_sticker": {
        "name": "Q版贴纸", "emoji": "🐣",
        "desc": "圆润 Q 版，透明贴纸风",
        "direction": "cute chibi sticker art: oversized head, tiny body, bold clean outline, flat vivid colors, die-cut sticker with white border",
        "tokens": "chibi sticker, big head tiny body, bold clean outline, flat vivid colors, white die-cut border, ",
    },
    "poster_minimal": {
        "name": "极简海报", "emoji": "◻️",
        "desc": "大留白版式，几何图形构成",
        "direction": "minimalist graphic poster: bold geometric shapes, generous empty space, limited 3-color palette, flat design",
        "tokens": "minimalist poster design, bold geometric shapes, generous negative space, limited palette, flat vector look, ",
    },
    "portrait_photo": {
        "name": "写真人像", "emoji": "📷",
        "desc": "85mm 人像，自然肤色质感",
        "direction": "professional portrait photography: 85mm lens, natural skin texture with pores, soft window light, creamy bokeh background",
        "tokens": "professional portrait photo, 85mm f1.4, natural skin texture, soft window light, creamy bokeh, ",
    },
    "vaporwave": {
        "name": "蒸汽波", "emoji": "🌴",
        "desc": "80 年代复古合成器美学",
        "direction": "vaporwave retro aesthetic: 1980s synthwave sunset grid, chrome text vibes, pastel pink and cyan gradient sky",
        "tokens": "vaporwave aesthetic, retro 80s synthwave, chrome gradients, pink cyan sunset grid, vhs grain, ",
    },
}


def get_style(sid):
    return STYLE_SOPS.get(sid or "", None)


# ---------------------------------------------------------------- prompt enhance (zh -> en)

_ZH_RE = re.compile(r"[\u4e00-\u9fff]")

# MyMemory 直译的高频误修 → Flux 友好词表
_TRANSLATION_FIXES = [
    ("national comedy", "Chinese donghua (guoman) animation"),
    ("national comic", "Chinese donghua animation"),
    ("close-up of the movie", "cinematic close-up"),
    ("movie feeling", "cinematic look"),
    ("the sea of clouds", "a sea of clouds"),
    ("looking back", "glancing back over the shoulder"),
]
_STYLE_BOOST = "cinematic lighting, highly detailed, guoman 3d animation style"


def translate_mymemory(text):
    q = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=zh-CN|en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        d = json.loads(r.read())
    en = (d.get("responseData") or {}).get("translatedText")
    if not en or "IS AN INVALID" in en.upper() or "MYMEMORY WARNING" in en.upper():
        raise ValueError("myMemory 无译文")
    return en


def polish_english(en):
    low = en
    for bad, good in _TRANSLATION_FIXES:
        low = low.replace(bad, good)
    # 去掉句尾多余的 "and"
    low = re.sub(r",\s*and\s*$", "", low)
    en = low.strip()
    if not en.endswith("."):
        en = en.rstrip(",;")
    return en + ", " + _STYLE_BOOST


def image_to_prompt(path):
    """图生文反推：读图 → 视觉 LLM 生成英文提示词。"""
    full = resolve_media(path)
    if not full or not os.path.isfile(full):
        return {"ok": False, "error": "图片不存在"}
    import base64
    ext = os.path.splitext(full)[1].lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(full, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    data_url = f"data:image/{mime};base64,{b64}"
    key = SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key") or ""
    if not key:
        return {"ok": False, "error": "未配置 API Key（图生文需要视觉模型）"}
    base = (SETTINGS.get("llm_base_url") or LLM_PRESETS.get(SETTINGS.get("llm_provider"), {}).get("base", "")).rstrip("/")
    model = SETTINGS.get("llm_model") or ""
    body = json.dumps({"model": model, "temperature": 0.3, "messages": [
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": "Reverse-engineer this image into a detailed English generation prompt (40-90 words): subject, action, environment, lighting, camera, style. Output only the prompt."}]}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read())
        return {"ok": True, "prompt": resp["choices"][0]["message"]["content"].strip()}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:150]
        hint = "当前模型可能不支持视觉输入，可换 glm-4v-flash 或其他视觉型号" if e.code == 400 else detail
        return {"ok": False, "error": f"反推失败：{hint}"}
    except Exception as e:
        return {"ok": False, "error": f"反推失败：{e}"}


def _llm_chat_full(messages, tools=None, temperature=0.3, timeout=60):
    """统一 LLM 通道（完整版）：返回 choices[0].message 对象（含 tool_calls 时 content 可能为 None）。"""
    provider = SETTINGS.get("llm_provider", "zhipu")
    base = (SETTINGS.get("llm_base_url") or LLM_PRESETS.get(provider, {}).get("base", "")).rstrip("/")
    key = SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key") or ""
    model = SETTINGS.get("llm_model") or SETTINGS.get("zhipu_model") or "glm-4-flash"
    if not key:
        raise RuntimeError("未配置 API Key（设置页 → AI 厂商）")
    if not base:
        raise RuntimeError("未配置接口地址（设置页 → AI 厂商）")
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]


def _llm_chat(messages, temperature=0.3, timeout=60):
    """统一 LLM 通道：OpenAI 兼容协议，按设置里的厂商/BaseURL/Key/模型调用。"""
    return (_llm_chat_full(messages, temperature=temperature, timeout=timeout).get("content") or "").strip()


def llm_models_fetch(provider, base_url=None, key=None):
    """拉取厂商模型列表（OpenAI 兼容 /models）。失败返回 None。"""
    preset = LLM_PRESETS.get(provider, {})
    base = (base_url or preset.get("base", "")).rstrip("/")
    key = key or SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key") or ""
    if not base:
        return None
    req = urllib.request.Request(base + "/models",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": "comfyagent"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return sorted(ids) or None
    except Exception:
        return None


_IMG_FORMULA = ("主体(the subject) → 动作/姿态 → 环境 → 光线 → 镜头/构图 → 艺术风格，"
                "写成一段连贯的自然语言长描述（Flux 的 T5 编码器吃密集描述，不要关键词堆砌）")

_VIDEO_FORMULA = ("一个连续镜头（5 秒内）：主体 → 主体动作/表情变化 → 运镜方式（缓慢推近/横移/固定机位）"
                  " → 环境与光线 → 环境音描述。遵守 h3lite 提示词规范：单一场景、动作幅度小、不写对白。")


def enhance_prompt(text, style_id=None, mode="image"):
    """中文→英文增强（风格感知）。返回 {ok, english, engine, note?}；已是英文则加风格令牌。"""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "空提示词"}
    style = get_style(style_id)
    if SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key"):
        try:
            formula = _VIDEO_FORMULA if mode == "video" else _IMG_FORMULA
            style_line = f"\n风格方向（务必贯彻）：{style['direction']}" if style else ""
            en = _llm_chat([
                {"role": "system", "content": (
                    f"你是{'视频' if mode == 'video' else '图像'}生成提示词专家。把用户的中文描述翻译并重写为"
                    f"一段 40-90 词的英文提示词。结构公式：{formula}{style_line}\n"
                    "只输出英文提示词本身，不要解释或引号。")},
                {"role": "user", "content": text},
            ])
            if style and style["tokens"].split(",")[0].strip().lower() not in en.lower():
                en = en.rstrip(".") + ", " + style["tokens"].rstrip(", ")
            return {"ok": True, "english": en, "engine": "llm", "style": style_id}
        except Exception as e:
            note = f"LLM 增强失败({e})，用免费翻译兜底"
    else:
        note = None
    try:
        en = polish_english(translate_mymemory(text))
        if style:
            en = en.rstrip(",;") + ", " + style["tokens"].rstrip(", ")
        en = en.rstrip(",") + ", " + QUALITY_TAIL
        return {"ok": True, "english": en, "engine": "mymemory", "note": note, "style": style_id}
    except Exception as e:
        return {"ok": False, "error": f"翻译失败：{e}" + ("；" + note if note else "") + "（将按原文提交）"}




# ---------------- 助手 function calling 工具循环 ----------------
AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "query_queue",
        "description": "查询 ComfyUI 当前状态：正在执行/排队的任务数、GPU 显存。用户问「状态/队列/现在怎么样」时用。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "search_gallery",
        "description": "按关键词搜索本地画廊（output 目录）成果文件，返回文件名/类型/时间。用户问「有没有…图/视频」时用。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "文件名关键词，空字符串=列出最新"},
            "limit": {"type": "integer", "description": "返回条数，默认 8，上限 20"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_log",
        "description": "读取应用运行日志（data/app.log）尾部若干行，用于排查错误。",
        "parameters": {"type": "object", "properties": {
            "lines": {"type": "integer", "description": "行数，默认 30，上限 200"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "launcher",
        "description": "操作 ComfyUI 启动器。action=status 只查状态；start/stop/restart 会真实启停 ComfyUI（用户明确要求时才用）。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["status", "start", "stop", "restart"]}}, "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "submit_generation",
        "description": "提交生成任务到 ComfyUI（会占用 GPU）。仅当用户明确要求生成图片/视频时使用；count 上限 4。",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "画面描述（中文即可，会自动增强为英文）"},
            "mode": {"type": "string", "enum": ["image", "video"]},
            "count": {"type": "integer", "description": "张数/条数，默认 1"}},
            "required": ["prompt"]}}},
]


def _tool_exec(name, args):
    """执行工具并返回摘要字符串（控制体积，供 LLM 阅读）。"""
    try:
        if name == "query_queue":
            q = COMFY.http("/queue", timeout=5)
            st = COMFY.probe() or {}
            dev = (st.get("devices") or [{}])[0]
            return (f"online={comfy_running()} running={len(q.get('queue_running', []))} "
                    f"pending={len(q.get('queue_pending', []))} "
                    f"vram_total_MB={dev.get('vram_total', 0) // (1 << 20)} "
                    f"vram_free_MB={dev.get('vram_free', 0) // (1 << 20)}")
        if name == "search_gallery":
            q = (args.get("query") or "").lower()
            limit = max(1, min(int(args.get("limit") or 8), 20))
            items = scan_gallery()
            if q:
                items = [i for i in items if q in i.get("name", "").lower() or q in i.get("path", "").lower()]
            if not items:
                return "no results"
            return "; ".join(f"{i.get('name')}|{'video' if i.get('kind') == 'video' else 'image'}|"
                             f"{i.get('mtime') and ''}{i.get('path')}" for i in items[:limit])
        if name == "read_log":
            n = max(1, min(int(args.get("lines") or 30), 200))
            logp = os.path.join(DATA_DIR, "app.log")
            if not os.path.isfile(logp):
                return "(log file not found)"
            with open(logp, "r", encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-n:]
            return "".join(l[-200:] if len(l) > 200 else l for l in tail) or "(empty)"
        if name == "launcher":
            action = args.get("action", "status")
            if action == "status":
                port = _comfy_port()
                return f"comfy_running={comfy_running()} port={port}"
            if action == "stop":
                return str(comfy_stop())
            if action == "start":
                return str(comfy_launch())
            if action == "restart":
                r1 = comfy_stop()
                time.sleep(1)
                return str(r1) + " -> " + str(comfy_launch())
            return "unknown action"
        if name == "submit_generation":
            prompt = (args.get("prompt") or "").strip()
            if not prompt:
                return "error: prompt is required"
            mode = args.get("mode", "image")
            count = max(1, min(int(args.get("count") or 1), 4))
            if mode == "video":
                wf = next((w for w in list_workflows() if w.get("id") == "h3-t2v"), None)
                if not wf:
                    return "error: video workflow not found"
                res = submit_workflow(wf, times=count, seed=None, overrides={"text": prompt})
                return str(res.get("msg") or res.get("error") or "submitted")
            enh = enhance_prompt(prompt)
            if enh.get("ok"):
                prompt = enh["english"]
            wf = BUILTIN_WORKFLOWS["Flux 文生图（内置）"]
            res = submit_workflow(wf, times=count, seed=None, overrides={"text": prompt})
            return str(res.get("msg") or res.get("error") or "submitted")
        return f"unknown tool: {name}"
    except Exception as e:
        return f"tool error: {e}"


AGENT_SYS = (
    "你是 ComfyAgent（本地 AI 创作台）的控制台助手。回答用户关于本机生成状态、画廊成果、日志、ComfyUI 启停的问题时，"
    "必须调用工具获取真实数据，禁止编造。生成类操作只在用户明确要求时执行，count 不超过 4。"
    "用简短中文回复，把工具返回的关键数字转成人话。"
)


def agent_tool_loop(text, max_rounds=6):
    """function calling 工具循环。厂商不支持 tools（HTTP 400 等）时抛异常由调用方回落。"""
    msgs = [{"role": "system", "content": AGENT_SYS}, {"role": "user", "content": text}]
    trace = []
    for _ in range(max_rounds):
        msg = _llm_chat_full(msgs, tools=AGENT_TOOLS, temperature=0.2, timeout=45)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": (msg.get("content") or "").strip() or "（无回复）", "tool_trace": trace}
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for tc in calls:
            fn = (tc.get("function") or {}).get("name", "")
            try:
                args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
            except Exception:
                args = {}
            result = _tool_exec(fn, args)
            trace.append({"tool": fn, "args": args, "summary": str(result)[:160]})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result})
    return {"reply": "（工具轮次达到上限，以下是目前掌握的信息）\n" + "\n".join(
        f"{t2['tool']}: {t2['summary']}" for t2 in trace), "tool_trace": trace}


def agent_intent_llm(text):
    """助手意图理解：统一 LLM 通道，输出 JSON 动作。"""
    return _llm_chat([
        {"role": "system", "content": (
            "你是 ComfyAgent 控制台助手，把用户中文指令转成 JSON 动作。单个动作用单个对象；需要多步时输出 {\"actions\":[动作1,动作2]}。可用动作："
            '{"run":{"workflow":"名称","times":1,"seed":null,"text":"提示词覆盖"},'
            '{"interrupt":{}},{"clear_queue":{}},{"status":{}},'
            '{"archive":{"count":5,"title":""}},{"open":{"view":"gallery"}}。'
            "只输出一个 JSON 对象，不要多余文字。无法理解则输出 {\"reply\":\"解释原因\"}")},
        {"role": "user", "content": text},
    ], temperature=0.1)


def agent_execute(text):
    """规则式指令解析 + 执行。返回 {reply, actions}。"""
    t = text.strip()
    acts, reply = [], ""

    def find_wf(name_frag):
        cands = [w for w in list_workflows() if name_frag.lower() in w["name"].lower()]
        return cands[0] if len(cands) >= 1 else None

    m = re.search(r"^跑\s+(.+?)(?:\s*[×xX*]\s*(\d+))?\s*(?:seed\s*=\s*(\d+))?$", t)
    m2 = re.search(r"^(?:运行|执行)\s+(.+?)(?:\s*[×xX*]\s*(\d+))?\s*(?:seed\s*=\s*(\d+))?$", t)
    mm = m or m2
    if mm:
        wf = find_wf(mm.group(1).strip())
        if not wf:
            reply = f"没找到名称包含「{mm.group(1)}」的工作流。已有：" + "、".join(w["name"] for w in list_workflows()[:10])
        else:
            times = int(mm.group(2) or 1)
            seed = int(mm.group(3)) if mm.group(3) else None
            res = submit_workflow(wf, times=times, seed=seed)
            reply = res.get("msg", "")
            acts.append({"type": "submitted", "prompt_ids": res.get("prompt_ids", [])})
    elif re.match(r"^(状态|status|队列|现在怎么样)", t):
        try:
            q = COMFY.http("/queue", timeout=5)
            st = COMFY.probe() or {}
            dev = (st.get("devices") or [{}])[0]
            reply = (f"ComfyUI 在线。正在执行 {len(q.get('queue_running', []))} 个，"
                     f"排队 {len(q.get('queue_pending', []))} 个。显存 {dev.get('vram_total', 0) // (1 << 20)}MB"
                     f"（空闲 {dev.get('vram_free', 0) // (1 << 20)}MB）。")
        except Exception:
            reply = "ComfyUI 不在线，先启动它（h3_launch.sh）。"
    elif re.search(r"(中断|停止|暂停|停掉)", t):
        try:
            COMFY.http("/interrupt", payload={}, timeout=5)
            reply = "已发送中断指令（只中断当前执行中的任务）。"
        except Exception as e:
            reply = f"中断失败：{e}"
    elif re.search(r"清空(队列)?", t):
        try:
            COMFY.http("/queue", payload={"clear": True}, timeout=5)
            reply = "队列已清空。"
        except Exception as e:
            reply = f"清空失败：{e}"
    elif re.search(r"归档(?:最近)?\s*(\d+)?\s*(张|个|条|个成果)?", t) and "归档" in t:
        n = int(re.search(r"(\d+)", t).group(1)) if re.search(r"(\d+)", t) else 5
        n = min(n, 30)
        items = scan_gallery()[:n]
        r = archive_media([i["path"] for i in items], title=f"最新{n}个成果")
        reply = (f"已把最新 {r.get('count', 0)} 个成果归档到知识库笔记 {r.get('note', '')}。"
                 if r.get("ok") else f"归档失败：{r.get('error')}")
        acts.append({"type": "archive", "uri": r.get("uri")})
    elif re.match(r"^打开\s*(最新|画廊|知识库|工作流|任务)?", t):
        view = {"最新": "gallery", "画廊": "gallery", "知识库": "obsidian", "工作流": "editor", "任务": "runs"}.get(
            re.match(r"^打开\s*(最新|画廊|知识库|工作流|任务)?", t).group(1) or "画廊", "gallery")
        acts.append({"type": "open", "view": view})
        reply = f"已切换到{view}。"
    elif re.search(r"^(画|生成|来)\s*(一张|一幅)?\s*(?:图|图片)?\s*[:：]?\s*(.+)", t):
        prompt_text = re.search(r"^(?:画|生成|来)\s*(?:一张|一幅)?\s*(?:图|图片)?\s*[:：]?\s*(.+)", t).group(1).strip()
        size = None
        ms = re.search(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})", prompt_text)
        if ms:
            size = (int(ms.group(1)), int(ms.group(2)))
            prompt_text = prompt_text[:ms.start()].strip()
        # 「用国漫史诗画：xxx」→ 风格感知（迭代24）
        style_id = None
        for sid, s in STYLE_SOPS.items():
            if s["name"] in prompt_text:
                style_id = sid
                prompt_text = prompt_text.replace(s["name"], "").strip("，,：: ")
                break
        enh = enhance_prompt(prompt_text, style_id=style_id)
        if enh.get("ok") and enh.get("english"):
            prompt_text = enh["english"]
        wf = BUILTIN_WORKFLOWS["Flux 文生图（内置）"]
        overrides = {"text": prompt_text}
        if size:
            overrides.update({"width": size[0], "height": size[1]})
        res = submit_workflow(wf, times=1, seed=None, overrides=overrides)
        reply = res.get("msg", "")
        acts.append({"type": "submitted", "prompt_ids": res.get("prompt_ids", [])})
    else:
        if SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key"):
            try:
                r = agent_tool_loop(t)
                if r and r.get("reply"):
                    return {"reply": r["reply"], "actions": acts, "tool_trace": r.get("tool_trace") or []}
            except Exception:
                pass  # 厂商不支持 tools / 网络失败 → 回落旧意图链路
            try:
                raw = agent_intent_llm(t)
                raw = raw.strip().strip("`")
                raw = re.sub(r"^json\s*", "", raw)
                obj = json.loads(raw)
                if "reply" in obj and len(obj) == 1:
                    reply = obj["reply"]
                elif "actions" in obj and isinstance(obj["actions"], list):
                    parts, acts = [], []
                    for a in obj["actions"][:6]:
                        r2 = agent_execute_coerce(a)
                        parts.append(r2.get("reply", ""))
                        acts.extend(r2.get("actions", []))
                    reply = "\n".join(p for p in parts if p) or "已完成全部动作"
                    return {"reply": reply, "actions": acts}
                else:
                    return agent_execute_coerce(obj)
            except Exception as e:
                reply = f"（LLM 解析失败：{e}）" + AGENT_HELP
        else:
            reply = AGENT_HELP
    return {"reply": reply, "actions": acts}


def agent_execute_coerce(obj):
    """把 LLM 输出的动作对象转成实际执行（递归复用规则层动作）。"""
    acts, reply = [], ""
    if isinstance(obj, dict):
        if "run" in obj:
            r = obj["run"]
            wf = None
            for w in list_workflows():
                if str(r.get("workflow", "")).lower() in w["name"].lower():
                    wf = w
                    break
            if wf:
                ov = {}
                if r.get("text"):
                    ov["text"] = r["text"]
                res = submit_workflow(wf, times=int(r.get("times", 1) or 1),
                                      seed=r.get("seed"), overrides=ov or None)
                reply = res.get("msg", "")
                acts.append({"type": "submitted", "prompt_ids": res.get("prompt_ids", [])})
            else:
                reply = "LLM 指定的工作流没找到。"
        elif "status" in obj:
            return agent_execute("状态")
        elif "interrupt" in obj:
            return agent_execute("中断")
        elif "clear_queue" in obj:
            return agent_execute("清空队列")
        elif "archive" in obj:
            return agent_execute(f"归档最近 {obj['archive'].get('count', 5)} 个")
        elif "open" in obj:
            return agent_execute("打开" + {"gallery": "画廊", "obsidian": "知识库", "editor": "工作流", "runs": "任务"}.get(
                obj["open"].get("view", "gallery"), "画廊"))
    if not reply:
        reply = AGENT_HELP
    return {"reply": reply, "actions": acts}


AGENT_HELP = ("我可以：\n"
              "· 「跑 Flux 文生图 ×3」/「运行 xxx seed=42」——提交工作流\n"
              "· 「画：雪夜少女 832x1216」——用 Flux 模板直接生图\n"
              "· 「状态 / 中断 / 清空队列」——控制台管理\n"
              "· 「归档最近 10 个」——最新成果写入 Obsidian\n"
              "· 「打开画廊/知识库/工作流」——页面跳转\n"
              "（设置里填智谱 API Key 后，其它说法我会用 GLM 帮你理解）")


# ---------------------------------------------------------------- prompt submit

def submit_workflow(wf, times=1, seed=None, overrides=None, params=None):
    """提交工作流到 ComfyUI，返回 {ok, msg, prompt_ids}。支持批量变 seed、参数覆盖与风格参数。"""
    api = json.loads(json.dumps(wf.get("api", {})))  # deep copy
    if not api:
        return {"ok": False, "msg": "工作流为空"}
    if params:
        # 风格 SOP 参数：steps → KSampler 系，guidance → Guidance 系
        for nid, node in api.items():
            ct = node.get("class_type", "")
            ins = node.get("inputs", {})
            if "KSampler" in ct and "steps" in params and "steps" in ins:
                ins["steps"] = int(params["steps"])
            if "Guidance" in ct and "guidance" in params and "guidance" in ins:
                ins["guidance"] = float(params["guidance"])
    if overrides:
        applied = 0
        image_name = overrides.pop("__image__", None)
        for nid, node in api.items():
            ins = node.get("inputs", {})
            ct = node.get("class_type", "")
            for k, v in overrides.items():
                if k in ins and isinstance(ins[k], (str, int, float)):
                    ins[k] = v
                    applied += 1
                elif k == "text":
                    # H3 等视频工作流的文本键叫 prompt/caption
                    for alt in ("prompt", "caption"):
                        if alt in ins and isinstance(ins[alt], str):
                            ins[alt] = v
                            applied += 1
                            break
            if image_name:
                # i2v 首帧：只改 LoadImage 的源图选择；first_frame 等连线输入保持不动
                # （i2v 模板里 first_frame 是 ["LoadImage节点", 0] 连线，覆盖会破坏图）
                if ct == "LoadImage" and "image" in ins:
                    ins["image"] = image_name
        if applied == 0 and "text" in overrides:
            # 常见场景：把 text 塞给第一个 CLIPTextEncode
            for nid, node in api.items():
                if node.get("class_type") == "CLIPTextEncode":
                    node["inputs"]["text"] = overrides["text"]
                    break
    # 找 seed 类输入用于随机化
    seed_nodes = []
    for nid, node in api.items():
        for k, v in (node.get("inputs") or {}).items():
            if re.search(r"seed", k, re.I) and isinstance(v, int):
                seed_nodes.append((nid, k))
    prompt_ids = []
    try:
        for i in range(max(1, min(times, 20))):
            if seed_nodes:
                use_seed = seed if seed is not None else random.randint(0, 2 ** 31 - 1)
                if seed is not None and times > 1:
                    use_seed = seed + i
                nid, k = seed_nodes[0]
                api[nid]["inputs"][k] = use_seed
            body = {"prompt": api, "client_id": SETTINGS["client_id"]}
            r = COMFY.http("/prompt", payload=body, timeout=30)
            if "prompt_id" not in r:
                return {"ok": False, "msg": "提交被拒绝：" + json.dumps(r, ensure_ascii=False)[:400]}
            pid = r["prompt_id"]
            prompt_ids.append(pid)
            cur_seed = api[seed_nodes[0][0]]["inputs"][seed_nodes[0][1]] if seed_nodes else None
            add_run({"prompt_id": pid, "name": wf.get("name", "未命名"), "seed": cur_seed,
                     "submitted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "queued",
                     "graph": json.loads(json.dumps(api))})
        n = len(prompt_ids)
        msg = f"已提交「{wf.get('name')}」×{n}（seed=" + (
            str(seed) if seed is not None else "随机") + "），到「任务」页看进度。"
        return {"ok": True, "msg": msg, "prompt_ids": prompt_ids}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return {"ok": False, "msg": f"ComfyUI 拒绝（{e.code}）：{detail}"}
    except Exception as e:
        return {"ok": False, "msg": f"提交失败：{e}（ComfyUI 在线吗？）"}


# ---------------------------------------------------------------- launcher (绘世式启动器)

_comfy_proc = {"handle": None}


def _comfy_port():
    try:
        return urllib.parse.urlparse(SETTINGS.get("comfy_url", "")).port or 8188
    except Exception:
        return 8188


def comfy_running():
    return COMFY.probe() is not None


def comfy_stop():
    """只杀监听 ComfyUI 端口的那个 PID（/T 连子进程），绝不波及其他进程。"""
    port = str(_comfy_port())
    r = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                       timeout=15, creationflags=0x08000000)
    pids = set()
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(":" + port) and "LISTENING" in line.upper():
            pids.add(parts[-1])
    if not pids:
        return {"ok": False, "msg": "没找到监听该端口的进程（可能已经停止）"}
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, creationflags=0x08000000)
    time.sleep(1.5)
    return {"ok": True, "msg": f"已停止 ComfyUI（PID {', '.join(sorted(pids))}）"}


def comfy_launch():
    if comfy_running():
        return {"ok": False, "msg": "ComfyUI 已在运行，无需重复启动"}
    exe = SETTINGS.get("comfy_python", "")
    cdir = SETTINGS.get("comfy_dir", "")
    if not os.path.isfile(exe):
        return {"ok": False, "msg": f"找不到 Python 解释器：{exe}（到启动器页修改）"}
    if not os.path.isdir(cdir):
        return {"ok": False, "msg": f"ComfyUI 目录不存在：{cdir}（到启动器页修改）"}
    try:
        args = shlex.split(SETTINGS.get("comfy_launch_args", ""))
    except ValueError:
        args = []
    logp = os.path.join(DATA_DIR, "comfy.log")
    lf = open(logp, "a", encoding="utf-8")
    proc = subprocess.Popen([exe, "main.py", *args], cwd=cdir, stdout=lf, stderr=subprocess.STDOUT,
                            creationflags=0x08000000 | 0x200)  # CREATE_NO_WINDOW | NEW_PROCESS_GROUP
    _comfy_proc["handle"] = proc
    return {"ok": True, "msg": f"ComfyUI 启动中（PID {proc.pid}）… 首次加载模型约 1-3 分钟，可到「启动器」页看日志"}


_ai_env_cache = {"ts": 0.0, "data": {}}


def launcher_info():
    cdir = SETTINGS.get("comfy_dir", "")
    models = {}
    for sub in ("checkpoints", "loras", "vae", "upscale_models", "controlnet"):
        p = os.path.join(cdir, "models", sub)
        items, total_size, count = [], 0, 0
        if os.path.isdir(p):
            allf = []
            for f in os.listdir(p):
                fp = os.path.join(p, f)
                if os.path.isfile(fp) and not f.startswith("put_"):
                    allf.append((f, os.path.getsize(fp)))
            allf.sort(key=lambda x: -x[1])
            count = len(allf)
            total_size = sum(s for _, s in allf)
            items = [{"name": n, "size": s} for n, s in allf[:30]]
        models[sub] = {"items": items, "count": count, "size": total_size}
    nodes_dir = os.path.join(cdir, "custom_nodes")
    nodes = []
    if os.path.isdir(nodes_dir):
        nodes = sorted(d for d in os.listdir(nodes_dir)
                       if os.path.isdir(os.path.join(nodes_dir, d)) and not d.startswith(("_", ".")))
    try:
        disk = shutil.disk_usage(SETTINGS.get("output_dir", BASE_DIR))
        disk_info = {"free": disk.free, "total": disk.total}
    except Exception:
        disk_info = None
    ai_env = {}
    # torch 探测要 fork 解释器 + import（秒级），而启动器页每 4s 轮询本接口——结果缓存 10 分钟
    if time.time() - _ai_env_cache["ts"] > 600:
        try:
            cpy = SETTINGS.get("comfy_python", "")
            if not cpy or not os.path.isfile(cpy):
                # 默认路径不存在（分发到其他机器）时自动探测 ComfyUI 自带解释器
                parent = os.path.dirname(cdir.rstrip("\\/")) if cdir else ""
                for cand in (os.path.join(cdir, "python_embeded", "python.exe"),
                             os.path.join(cdir, "venv", "Scripts", "python.exe"),
                             os.path.join(parent, "python", "python.exe")):
                    if os.path.isfile(cand):
                        cpy = cand
                        break
            if cpy and os.path.isfile(cpy):
                probe = (
                    "import torch, importlib.metadata as im, json\n"
                    "def _v(p):\n"
                    "    try:\n"
                    "        return im.version(p)\n"
                    "    except Exception:\n"
                    "        return ''\n"
                    "print(json.dumps({'torch': torch.__version__, 'triton-windows': _v('triton-windows'), 'sageattention': _v('sageattention')}))\n"
                )
                r = subprocess.run([cpy, "-c", probe], capture_output=True, text=True, timeout=30,
                                   encoding="utf-8", errors="replace", creationflags=0x08000000)
                if r.returncode == 0 and r.stdout.strip():
                    jlines = [l for l in r.stdout.strip().splitlines() if l.strip().startswith("{")]
                    d = json.loads(jlines[-1])
                    ai_env = {"torch": d.get("torch", ""),
                              "triton-windows": d.get("triton-windows", ""),
                              "sageattention": d.get("sageattention", "")}
        except Exception:
            pass
        _ai_env_cache["ts"] = time.time()
        _ai_env_cache["data"] = ai_env
    else:
        ai_env = _ai_env_cache["data"]
    return {
        "comfy_dir": cdir, "models": models, "nodes": nodes, "disk": disk_info,
        "python_version": sys.version.split()[0], "ffmpeg": bool(FFMPEG),
        "running": comfy_running(), "port": _comfy_port(),
        "ai_env": ai_env,
    }


# ---------------------------------------------------------------- comfyui version maintenance

def comfy_git_info():
    cdir = SETTINGS.get("comfy_dir", "")
    if not os.path.isdir(os.path.join(cdir, ".git")):
        return {"git": False}

    def g(*a, timeout=30):
        return subprocess.run(["git", *a], cwd=cdir, capture_output=True, text=True,
                              timeout=timeout, creationflags=0x08000000)

    head = (g("rev-parse", "--short", "HEAD").stdout or "").strip()
    branch = (g("rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()
    lines = (g("status", "--porcelain").stdout or "").splitlines()
    dirty_tracked = len([l for l in lines if not l.startswith("??")])
    ui_ver = None
    try:
        ui_ver = COMFY.http("/system_stats", timeout=4).get("system", {}).get("comfyui_version")
    except Exception:
        pass
    return {"git": True, "head": head, "branch": branch, "dirty_tracked": dirty_tracked, "ui_version": ui_ver}


def comfy_check_remote():
    """fetch 远端并计算落后多少个提交。返回 {ok, behind, remote_head, error?}"""
    info = comfy_git_info()
    if not info.get("git"):
        return {"ok": False, "error": "ComfyUI 目录不是 git 仓库"}
    cdir = SETTINGS.get("comfy_dir", "")

    def g(*a, timeout=180):
        return subprocess.run(["git", *a], cwd=cdir, capture_output=True, text=True,
                              timeout=timeout, creationflags=0x08000000)

    ls = g("ls-remote", "origin", "HEAD", timeout=30)
    if ls.returncode != 0:
        return {"ok": False, "error": "无法连接远端（网络问题或被墙）：" + ls.stderr.strip()[:120]}
    remote_sha = (ls.stdout or "").split()[0] if ls.stdout else ""
    f = g("fetch", "origin", "--quiet", timeout=180)
    if f.returncode != 0:
        return {"ok": False, "error": "fetch 失败：" + f.stderr.strip()[:120]}
    cnt = g("rev-list", "--count", f"HEAD..{remote_sha}")
    behind = int(cnt.stdout.strip() or 0) if cnt.returncode == 0 else 0
    return {"ok": True, "behind": behind, "remote_head": remote_sha[:7], **{k: info[k] for k in ("head", "branch", "ui_version")}}


def comfy_do_update():
    """一键更新：stash 本地改动 → ff-only pull → 恢复改动。"""
    info = comfy_git_info()
    if not info.get("git"):
        return {"ok": False, "msg": "ComfyUI 目录不是 git 仓库，无法一键更新"}
    cdir = SETTINGS.get("comfy_dir", "")

    def g(*a, timeout=240):
        return subprocess.run(["git", *a], cwd=cdir, capture_output=True, text=True,
                              timeout=timeout, creationflags=0x08000000)

    stashed = False
    if info.get("dirty_tracked", 0) > 0:
        g("stash", "push", "-q", "-m", "comfyagent-auto-stash")
        stashed = True
    pull = g("pull", "--ff-only", timeout=240)
    if pull.returncode != 0:
        if stashed:
            g("stash", "pop")
        return {"ok": False, "msg": "更新失败（已恢复本地改动）：" + (pull.stderr or pull.stdout).strip()[:200]}
    new_head = (g("rev-parse", "--short", "HEAD").stdout or "").strip()
    popped = ""
    if stashed:
        pop = g("stash", "pop")
        popped = "本地改动已恢复" if pop.returncode == 0 else "注意：本地改动恢复有冲突，在 git stash list 里"
    return {"ok": True, "msg": f"ComfyUI 已更新：{info.get('head')} → {new_head}。{popped}",
            "note": "需要重启 ComfyUI 生效（启动器页可一键重启）", "head": new_head}


# ---------------------------------------------------------------- obsidian vault visualization

def vault_scan():
    """扫描整个 vault：笔记列表 + 字数 + wiki 双链。"""
    v = SETTINGS.get("vault_path", "")
    notes = []
    if not os.path.isdir(v):
        return notes
    for dirpath, dirnames, filenames in os.walk(v):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                st = os.stat(fp)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            rel = os.path.relpath(fp, v).replace("\\", "/")
            links = re.findall(r"\[\[([^\]|#]+)", text)
            notes.append({"path": rel, "name": fn[:-3], "mtime": int(st.st_mtime),
                          "words": len(text), "links": [l.strip() for l in links]})
    notes.sort(key=lambda x: -x["mtime"])
    return notes


def vault_note_content(rel):
    v = os.path.abspath(SETTINGS.get("vault_path", ""))
    fp = os.path.abspath(os.path.join(v, rel))
    if not fp.lower().startswith(v.lower()) or not fp.endswith(".md") or not os.path.isfile(fp):
        return None
    with open(fp, encoding="utf-8", errors="replace") as f:
        return f.read(8000)


# ---------------------------------------------------------------- watchdog & auto-resume

_watch = {"last_online": None, "last_restart": 0.0}


def resume_stale_runs():
    """ComfyUI 重启后，把中断的排队/执行中任务按图快照重新提交（同 seed 保证可复现）。"""
    runs = load_runs()
    n = 0
    for r in runs:
        if r.get("status") in ("queued", "running") and r.get("graph"):
            res = submit_workflow({"name": "续跑·" + r.get("name", ""), "api": r["graph"]},
                                  times=1, seed=r.get("seed"))
            if res.get("ok"):
                n += 1
                r["status"] = "superseded"
                r["resumed_as"] = (res.get("prompt_ids") or [None])[0]
    if n:
        write_json_file(RUNS_FILE, runs[:300])
    return n


def watchdog_loop():
    """看门狗：ComfyUI 掉线自动重启；重启成功后自动续跑中断任务。"""
    startup_probed = False
    while True:
        time.sleep(8)
        try:
            online = COMFY.probe() is not None
        except Exception:
            online = False
        was = _watch["last_online"]
        if was is None:
            _watch["last_online"] = online
            if not online and not startup_probed and SETTINGS.get("comfy_watchdog", True):
                # 应用启动时 ComfyUI 就不在线 → 直接自动拉起（补盲区）
                startup_probed = True
                _watch["last_restart"] = time.time()
                r = comfy_launch()
                HUB.publish({"type": "watchdog", "data": {"phase": "restart", "ok": r.get("ok"), "msg": r.get("msg", r.get("error", ""))}})
            continue
        if was and not online:
            HUB.publish({"type": "watchdog", "data": {"phase": "down"}})
            time.sleep(10)
            still_down = True
            try:
                still_down = COMFY.probe() is None
            except Exception:
                pass
            if still_down and time.time() - _watch["last_restart"] > 180 and SETTINGS.get("comfy_watchdog", True):
                _watch["last_restart"] = time.time()
                r = comfy_launch()
                HUB.publish({"type": "watchdog", "data": {"phase": "restart", "ok": r.get("ok"), "msg": r.get("msg", r.get("error", ""))}})
                if r.get("ok"):
                    for _ in range(60):  # 最多等 10 分钟上线
                        time.sleep(10)
                        try:
                            if COMFY.probe():
                                break
                        except Exception:
                            pass
                    if SETTINGS.get("comfy_autorequeue", True):
                        try:
                            n = resume_stale_runs()
                            HUB.publish({"type": "watchdog", "data": {"phase": "resumed", "count": n}})
                        except Exception:
                            pass
        if not was and online:
            HUB.publish({"type": "watchdog", "data": {"phase": "up"}})
        _watch["last_online"] = online


# ---------------------------------------------------------------- batches (产线批次)

BATCH_DIR = os.path.join(DATA_DIR, "batches")
CHAR_DIR = os.path.join(DATA_DIR, "characters")


def _batch_path(bid):
    return os.path.join(BATCH_DIR, safe_name(bid) + ".json")


def _list_batches():
    out = []
    if os.path.isdir(BATCH_DIR):
        for fn in sorted(os.listdir(BATCH_DIR)):
            if fn.endswith(".json"):
                b = read_json_file(os.path.join(BATCH_DIR, fn), None)
                if b:
                    out.append({"id": b.get("id"), "name": b.get("name"), "created": b.get("created"),
                                "total": len(b.get("items", [])),
                                "done": sum(1 for i in b.get("items", []) if i.get("status") == "success"),
                                "failed": sum(1 for i in b.get("items", []) if i.get("status") == "error")})
    return out


def _load_batch(bid):
    return read_json_file(_batch_path(bid), None)


def _save_batch(b):
    write_text_atomic(_batch_path(b["id"]), json.dumps(b, ensure_ascii=False, indent=1))


def parse_script_text(text):
    """解析分集脚本：提取 ### SHOT编号【画风】 + ```text 块 的逐镜提示词。"""
    items = []
    pattern = re.compile(r"###\s*(\S+?)\s*[【\[]([^】\]]*)[】\]]\s*```[^\n]*\n(.*?)```", re.S)
    for m in pattern.finditer(text or ""):
        shot_id, style_tag, block = m.group(1), m.group(2).strip(), m.group(3).strip()
        items.append({"name": shot_id + (f"·{style_tag}" if style_tag else ""), "prompt": block})
    # 兜底：管道表格行（| SHOT01 | ... |）
    if not items:
        for line in (text or "").splitlines():
            mm = re.match(r"\|\s*(SHOT\w+|\S*E\d+S?\d*\w*)\s*\|", line, re.I)
            if mm and "|" in line[mm.end():]:
                cells = [c.strip() for c in line.strip("|").split("|")]
                items.append({"name": cells[0], "prompt": " / ".join(c for c in cells[1:] if c)})
    return items


def copy_to_input(src_rel, tag="frame"):
    """把画廊里的图复制进 ComfyUI input 目录（作 i2v 关键帧/参考图）。返回 input 文件名。"""
    full = resolve_media(src_rel)
    if not full or not os.path.isfile(full):
        return None
    cdir = SETTINGS.get("comfy_dir", "")
    input_dir = os.path.join(cdir, "input")
    if not os.path.isdir(input_dir):
        return None
    base = safe_name(os.path.splitext(os.path.basename(src_rel))[0])[:40] or tag
    name = f"agent_{tag}_{base}{os.path.splitext(full)[1]}"
    dst = os.path.join(input_dir, name)
    shutil.copy2(full, dst)  # 同名覆盖：幂等，重试不产生副本膨胀
    return name


def run_batch(bid, only_index=None, draft=False):
    b = _load_batch(bid)
    if not b:
        return {"ok": False, "msg": "批次不存在"}
    wf_id = b.get("workflow_id")
    if draft and wf_id in DRAFT_MAP:
        wf_id = DRAFT_MAP[wf_id]  # 草稿快跑：映射到对应 T8 草稿档（同 seed 不可复现，仅选镜用）
    wf = None
    for w in list_workflows():
        if w.get("id") == wf_id:
            wf = w
            break
    if not wf:
        wf = BUILTIN_WORKFLOWS["Flux 文生图（内置）"]
    # 优先级排序：priority=true 的镜头排前面
    indices = list(range(len(b.get("items", []))))
    if only_index is not None:
        indices = [only_index]
    else:
        indices.sort(key=lambda i: (not b["items"][i].get("priority", False), i))
    queued = 0
    for i in indices:
        item = b["items"][i]
        if only_index is None and item.get("status") == "success":
            continue
        overrides = {"text": item.get("prompt", "")}
        # 关键帧：镜头指定了首帧图 → 复制进 input 目录并注入图输入
        if item.get("first_frame"):
            input_name = copy_to_input(item["first_frame"], tag="ff")
            if input_name:
                overrides["__image__"] = input_name
            else:
                item["status"] = "error"
                item["error"] = f"关键帧图无效：{item['first_frame']}"
                continue
        res = submit_workflow({"name": f"{b['name']}·{item['name']}", "api": wf["api"]},
                              times=1, seed=None,
                              overrides=overrides,
                              params=item.get("params"))
        if res.get("ok"):
            item["status"] = "queued"
            item["prompt_id"] = (res.get("prompt_ids") or [None])[0]
            item["started"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            queued += 1
        else:
            item["status"] = "error"
            item["error"] = (res.get("msg") or "")[:200]
    b["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_batch(b)
    return {"ok": True, "msg": f"已排队 {queued}/{len(b.get('items', []))} 个镜头", "batch": b}


def batch_sync_status():
    """用 ComfyUI history 刷新所有批次里 queued/running 的状态。"""
    try:
        h = COMFY.http("/history?max_items=100", timeout=10)
    except Exception:
        return
    hmap = {}
    for pid, item in (h or {}).items():
        st = (item.get("status") or {}).get("status_str")
        outs = []
        for o in (item.get("outputs") or {}).values():
            for key in ("images", "gifs", "videos"):
                for im in (o.get(key) or []):
                    outs.append(((o.get("subfolder", "") + "/" if o.get("subfolder") else "") + im.get("filename", "")))
        hmap[pid] = (st, outs)
    if not os.path.isdir(BATCH_DIR):
        return
    for fn in os.listdir(BATCH_DIR):
        if not fn.endswith(".json"):
            continue
        b = read_json_file(os.path.join(BATCH_DIR, fn), None)
        if not b:
            continue
        changed = False
        for item in b.get("items", []):
            pid = item.get("prompt_id")
            if pid and pid in hmap and item.get("status") in ("queued", "running", None):
                stt, outs = hmap[pid]
                item["status"] = "success" if stt == "success" else ("error" if stt == "error" else item.get("status"))
                if outs:
                    item["output"] = outs[0]
                if item["status"] == "success":
                    item["completed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if item.get("started") and not item.get("duration"):
                        try:
                            stp = datetime.strptime(item["started"], "%Y-%m-%d %H:%M:%S")
                            item["duration"] = round((datetime.now() - stp).total_seconds() / 60, 1)
                        except Exception:
                            pass
                changed = True
                # 失败自动换种子重试（最多 batch_auto_retry 次）
                if item["status"] == "error":
                    max_retry = int(SETTINGS.get("batch_auto_retry", 2))
                    if item.get("retry_count", 0) < max_retry:
                        wf = next((w for w in list_workflows() if w.get("id") == b.get("workflow_id")), BUILTIN_WORKFLOWS["Flux 文生图（内置）"])
                        ov = {"text": item.get("prompt", "")}
                        if item.get("first_frame"):
                            input_name = copy_to_input(item["first_frame"], tag="ff")
                            if input_name:
                                ov["__image__"] = input_name
                        res = submit_workflow({"name": f"{b['name']}·{item['name']}·重试{item.get('retry_count', 0) + 1}", "api": wf["api"]},
                                              times=1, seed=None, overrides=ov, params=item.get("params"))
                        if res.get("ok"):
                            item["retry_count"] = item.get("retry_count", 0) + 1
                            item["status"] = "queued"
                            item["prompt_id"] = (res.get("prompt_ids") or [None])[0]
                            item["started"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"* batch auto-retry: {item['name']} 第{item['retry_count']}次")
        if changed:
            write_json_file(_batch_path(b.get("id")), b)


# ---------------------------------------------------------------- characters (角色资产库)

def _char_path(cid):
    return os.path.join(CHAR_DIR, safe_name(cid) + ".json")


def list_characters():
    out = []
    if os.path.isdir(CHAR_DIR):
        for fn in sorted(os.listdir(CHAR_DIR)):
            if fn.endswith(".json"):
                c = read_json_file(os.path.join(CHAR_DIR, fn), None)
                if c:
                    out.append(c)
    return out


# ---------------------------------------------------------------- template library (ComfyUI 模板库代理)

TPL_MIRRORS = [
    "https://cdn.jsdelivr.net/gh/Comfy-Org/workflow_templates@main/templates/",
    "https://gcore.jsdelivr.net/gh/Comfy-Org/workflow_templates@main/templates/",
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/",
]
TPL_INDEX_CACHE = os.path.join(CACHE_DIR, "templates_index.json")
TPL_CACHE = os.path.join(CACHE_DIR, "templates")


def tpl_fetch(rel, timeout=25):
    """从镜像链拉取模板库文件（index/工作流JSON/媒体），24h 磁盘缓存。"""
    rel = rel.lstrip("/")
    if ".." in rel:
        raise RuntimeError("illegal path")
    if not os.path.isdir(TPL_CACHE):
        os.makedirs(TPL_CACHE, exist_ok=True)
    dst = os.path.join(TPL_CACHE, hashlib.sha1(rel.encode()).hexdigest() + "_" + os.path.basename(rel))
    if os.path.isfile(dst) and time.time() - os.path.getmtime(dst) < 86400:
        return dst
    last = "unknown"
    for m in TPL_MIRRORS:
        try:
            req = urllib.request.Request(m + urllib.parse.quote(rel), headers={"User-Agent": "comfyagent"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if not data:
                continue
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dst)
            return dst
        except Exception as e:
            last = str(e)
    raise RuntimeError(last)


def tpl_index():
    if os.path.isfile(TPL_INDEX_CACHE) and time.time() - os.path.getmtime(TPL_INDEX_CACHE) < 86400:
        return read_json_file(TPL_INDEX_CACHE, None)
    try:
        p = tpl_fetch("index.json", timeout=30)
        data = read_json_file(p, None)
        if data:
            write_text_atomic(TPL_INDEX_CACHE, json.dumps(data, ensure_ascii=False))
            return data
    except Exception:
        pass
    return read_json_file(TPL_INDEX_CACHE, None)  # 过期缓存兜底


# ---------------------------------------------------------------- scenes (场景库)

SCENE_DIR = os.path.join(DATA_DIR, "scenes")


def list_scenes():
    out = []
    if os.path.isdir(SCENE_DIR):
        for fn in sorted(os.listdir(SCENE_DIR)):
            if fn.endswith(".json"):
                s = read_json_file(os.path.join(SCENE_DIR, fn), None)
                if s:
                    out.append(s)
    return out


# ---------------------------------------------------------------- episodes (集数聚合)

def batch_episodes():
    """按批次名前缀提取集数聚合。"""
    eps = {}
    for b in _list_batches():
        bid_full = _load_batch(b["id"])
        if not bid_full:
            continue
        ep_key = b["name"].split("_")[0].split("·")[0].strip() or "未分组"
        if ep_key not in eps:
            eps[ep_key] = {"name": ep_key, "batches": [], "total": 0, "done": 0, "failed": 0,
                           "gpu_minutes": 0.0, "outputs": []}
        for item in bid_full.get("items", []):
            eps[ep_key]["total"] += 1
            if item.get("status") == "success":
                eps[ep_key]["done"] += 1
                if item.get("duration"):
                    eps[ep_key]["gpu_minutes"] += item["duration"]
                if item.get("output"):
                    eps[ep_key]["outputs"].append(item["output"])
            elif item.get("status") == "error":
                eps[ep_key]["failed"] += 1
        eps[ep_key]["batches"].append(b["id"])
    return sorted(eps.values(), key=lambda x: -x["total"])


# ---------------------------------------------------------------- audio assets

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}


def scan_audio_assets():
    """扫描 output 目录及子目录中的音频文件。"""
    root = SETTINGS.get("output_dir", "")
    out = []
    if not os.path.isdir(root):
        return out
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                fp = os.path.join(dp, f)
                try:
                    st = os.stat(fp)
                    out.append({"path": os.path.relpath(fp, root).replace("\\", "/"),
                                "name": f, "size": st.st_size, "mtime": int(st.st_mtime)})
                except OSError:
                    pass
    out.sort(key=lambda x: -x["mtime"])
    return out


# ---------------------------------------------------------------- style induction

def induce_style_from_images(paths):
    """多张图 → GLM 视觉归纳共同风格关键词。"""
    import base64
    key = SETTINGS.get("llm_key") or SETTINGS.get("zhipu_key") or ""
    if not key:
        return {"ok": False, "error": "未配置 API Key"}
    base = (SETTINGS.get("llm_base_url") or LLM_PRESETS.get(SETTINGS.get("llm_provider"), {}).get("base", "")).rstrip("/")
    model = SETTINGS.get("llm_model") or ""
    content = [{"type": "text", "text": "分析这些图片的共同视觉风格。输出一段 30-60 词的英文风格描述（style tokens），可直接用作生成提示词的风格后缀。只输出风格描述。"}]
    for p in paths[:4]:
        full = resolve_media(p)
        if not full or not os.path.isfile(full):
            continue
        ext = os.path.splitext(full)[1].lower().lstrip(".")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}})
    if len(content) < 2:
        return {"ok": False, "error": "没有有效图片"}
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 200}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    return {"ok": True, "style": resp["choices"][0]["message"]["content"].strip()}


# ---------------------------------------------------------------- subtitle burn

def burn_subtitles(video_path, srt_path, out_path):
    """ffmpeg srt 字幕烧入。"""
    srt_esc = srt_path.replace("\\", "/").replace(":", "\:").replace("'", "\'")
    r = subprocess.run([FFMPEG, "-v", "error", "-i", video_path,
                        "-vf", f"subtitles='{srt_esc}':force_style='FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=1'",
                        "-c:a", "copy", "-y", out_path],
                       capture_output=True, text=True, timeout=600, creationflags=0x08000000)
    return r.returncode == 0


# ---------------------------------------------------------------- HTTP handler

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ComfyAgent/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    # ---- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def send_file(self, path, mime, ranges=None, download_name=None):
        try:
            size = os.path.getsize(path)
        except OSError:
            self.send_json({"ok": False, "error": "file missing"}, 404)
            return
        f = open(path, "rb")
        start, end = 0, size - 1
        code = 200
        if ranges:
            m = re.match(r"bytes=(\d*)-(\d*)", ranges)
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
                elif not m.group(1):
                    start = max(0, size - int(m.group(2) or size))
                code = 206
        clen = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(clen))
        # 本地静态资源：禁止缓存，保证更新后前端立即生效
        self.send_header("Cache-Control", "no-store")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download_name:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" +
                             urllib.parse.quote(download_name))
        self.end_headers()
        try:
            f.seek(start)
            remaining = clen
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)
        finally:
            f.close()

    # ---- routing
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        try:
            u = urllib.parse.urlparse(self.path)
            path, q = u.path, dict(urllib.parse.parse_qsl(u.query))
            body = self.read_body() if method == "POST" else {}

            if path.startswith("/api/"):
                return self.api(method, path, q, body)
            if method != "GET":
                return self.send_json({"ok": False, "error": "bad method"}, 405)
            # 静态文件
            if path in ("/", "/index.html"):
                return self.send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            fp = os.path.abspath(os.path.join(STATIC_DIR, path.lstrip("/")))
            if not fp.lower().startswith(os.path.abspath(STATIC_DIR).lower()) or not os.path.isfile(fp):
                return self.send_json({"ok": False, "error": "not found"}, 404)
            mime = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            if fp.endswith(".js"):
                mime = "text/javascript"
            return self.send_file(fp, mime, ranges=self.headers.get("Range"))
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                self.send_json({"ok": False, "error": str(e)}, 500)
            except Exception:
                pass

    def api(self, method, path, q, body):
        # ---- 设置/状态
        if path == "/api/settings" and method == "GET":
            s = dict(SETTINGS)
            s["has_zhipu_key"] = bool(s.get("zhipu_key"))
            s["has_llm_key"] = bool(s.get("llm_key") or s.get("zhipu_key"))
            s.pop("zhipu_key", None)
            s.pop("llm_key", None)
            s.pop("gitee_token", None)
            s.pop("client_id", None)
            return self.send_json({"ok": True, "settings": s})
        if path == "/api/settings" and method == "POST":
            # gitee_repo/gitee_token 内置不外露；zhipu_key/llm_key/gitee_token 走下方专用分支
            for k in ("port", "comfy_url", "output_dir", "vault_path",
                      "comfy_dir", "comfy_python", "comfy_launch_args",
                      "llm_provider", "llm_base_url", "llm_model",
                      "comfy_watchdog", "comfy_autorequeue", "batch_auto_retry", "lan_access"):
                if k in body:
                    SETTINGS[k] = body[k]
            if body.get("zhipu_key"):
                SETTINGS["zhipu_key"] = body["zhipu_key"]
            if body.get("gitee_token"):
                SETTINGS["gitee_token"] = body["gitee_token"]
            if body.get("llm_key"):
                SETTINGS["llm_key"] = body["llm_key"]
            save_settings(SETTINGS)
            _gallery_cache["ts"] = 0
            return self.send_json({"ok": True, "msg": "已保存（端口改动需重启服务）"})

        if path == "/api/status":
            st = COMFY.probe()
            gal = scan_gallery()
            version = "3.1.0"
            try:
                version = open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8").read().strip() or version
            except Exception:
                pass
            return self.send_json({"ok": True, "comfy_online": st is not None, "system_stats": st,
                                   "media_count": len(gal), "latest_mtime": gal[0]["mtime"] if gal else 0,
                                   "ws_state": HUB.state, "ffmpeg": bool(FFMPEG), "version": f"v{version}"})
        if path == "/api/logs":
            try:
                logp = os.path.join(DATA_DIR, "app.log")
                with open(logp, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-200:]
                return self.send_json({"ok": True, "lines": "".join(lines) or "（暂无日志）"})
            except Exception:
                return self.send_json({"ok": True, "lines": "（暂无日志）"})

        if path == "/api/broadcast/reload" and method == "POST":
            HUB.publish({"type": "force_reload"})
            return self.send_json({"ok": True, "msg": "已广播刷新，所有打开的窗口将自动重载"})
        if path == "/api/hardware":
            return self.send_json({"ok": True, **get_hardware()})

        # ---- ComfyUI 代理
        if path == "/api/queue":
            qd = COMFY.http("/queue", timeout=8)
            return self.send_json({"ok": True, "queue": qd})
        if path == "/api/history":
            limit = q.get("limit", "30")
            h = COMFY.http(f"/history?max_items={urllib.parse.quote(str(limit))}", timeout=15)
            runs = {r["prompt_id"]: r for r in load_runs()}
            out = []
            for pid, item in list(h.items())[:int(limit)]:
                status = item.get("status", {})
                outputs = []
                for nid, o in (item.get("outputs") or {}).items():
                    for key in ("images", "gifs", "videos", "audio"):
                        for im in (o.get(key) or []):
                            outputs.append({"filename": im.get("filename"), "subfolder": im.get("subfolder", ""),
                                            "type": im.get("type", "output")})
                out.append({"prompt_id": pid, "status": status.get("status_str"),
                            "completed": status.get("completed"), "outputs": outputs,
                            "name": runs.get(pid, {}).get("name", "")})
            out.sort(key=lambda x: runs.get(x["prompt_id"], {}).get("submitted", ""), reverse=True)
            return self.send_json({"ok": True, "history": out})
        if path == "/api/object_info":
            return self.send_json({"ok": True, "object_info": COMFY.object_info()})
        if path == "/api/comfyview":
            qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in q.items())
            try:
                with urllib.request.urlopen(COMFY.base + "/view?" + qs, timeout=30) as r:
                    data = r.read()
                    self.send_response(200)
                    self.send_header("Content-Type", r.headers.get("Content-Type", "application/octet-stream"))
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 502)

        # ---- 提交/控制
        if path == "/api/prompt" and method == "POST":
            wf = {"name": body.get("name") or "未命名", "api": body.get("prompt") or body.get("api")}
            res = submit_workflow(wf, times=int(body.get("times", 1) or 1),
                                  seed=body.get("seed"), overrides=body.get("overrides"),
                                  params=body.get("params"))
            return self.send_json(res)
        if path == "/api/runs":
            runs = [{k: v for k, v in r.items() if k != "graph"} | {"has_graph": bool(r.get("graph"))}
                    for r in load_runs()]
            return self.send_json({"ok": True, "runs": runs[:60]})
        if path == "/api/rerun" and method == "POST":
            pid = body.get("prompt_id", "")
            run = next((r for r in load_runs() if r.get("prompt_id") == pid), None)
            if not run or not run.get("graph"):
                return self.send_json({"ok": False, "msg": "找不到该任务的图快照（旧任务不支持一键重试）"})
            res = submit_workflow({"name": "重试·" + run.get("name", ""), "api": run["graph"]}, times=1, seed=None)
            return self.send_json(res)
        if path == "/api/interrupt" and method == "POST":
            COMFY.http("/interrupt", payload={}, timeout=8)
            return self.send_json({"ok": True, "msg": "已中断当前任务"})
        if path == "/api/clear_queue" and method == "POST":
            COMFY.http("/queue", payload={"clear": True}, timeout=8)
            return self.send_json({"ok": True, "msg": "队列已清空"})

        # ---- 画廊
        if path == "/api/gallery":
            items = scan_gallery(force=q.get("force") == "1")
            return self.send_json({"ok": True, "items": items, "root": SETTINGS["output_dir"]})
        if path == "/api/media":
            rel = q.get("path", "")
            full = resolve_media(rel)
            if not full or not os.path.isfile(full):
                return self.send_json({"ok": False, "error": "bad path"}, 404)
            ext = os.path.splitext(full)[1].lower()
            mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if q.get("thumb") == "1":
                tp = thumb_path_for(rel, os.path.getmtime(full))
                if not os.path.exists(tp):
                    ok = (make_video_thumb if ext in VIDEO_EXTS else make_image_thumb)(full, tp)
                    if not ok:
                        return self.send_json({"ok": False, "error": "thumb failed"}, 500)
                return self.send_file(tp, "image/jpeg", ranges=self.headers.get("Range"))
            return self.send_file(full, mime, ranges=self.headers.get("Range"),
                                  download_name=os.path.basename(full) if q.get("download") == "1" else None)
        if path == "/api/media/meta":
            rel = q.get("path", "")
            full = resolve_media(rel)
            if not full or not os.path.isfile(full):
                return self.send_json({"ok": False, "error": "bad path"}, 404)
            it = next((i for i in scan_gallery() if i["path"] == rel), {})
            meta = {"item": it}
            if full.lower().endswith(".png"):
                pm = png_workflow_meta(full)
                meta["prompt"] = pm.get("prompt")
                meta["workflow_ui"] = pm.get("workflow")
                meta["summary"] = summarize_api_graph(pm.get("prompt")) if pm.get("prompt") else None
            return self.send_json({"ok": True, **meta})
        if path == "/api/media/trash" and method == "POST":
            dst_dir = os.path.join(TRASH_DIR, datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.makedirs(dst_dir, exist_ok=True)
            n = 0
            for rel in body.get("paths", []):
                full = resolve_media(rel)
                if full and os.path.isfile(full):
                    shutil.move(full, os.path.join(dst_dir, os.path.basename(full)))
                    n += 1
            _gallery_cache["ts"] = 0
            return self.send_json({"ok": True, "count": n, "msg": f"已移入回收站 {n} 个文件"})
        if path == "/api/media/reveal" and method == "POST":
            full = resolve_media(body.get("path", ""))
            if full and os.path.isfile(full):
                subprocess.Popen(["explorer", "/select,", full])
                return self.send_json({"ok": True})
            return self.send_json({"ok": False, "error": "bad path"}, 404)

        # ---- 工作流
        if path == "/api/workflows" and method == "GET":
            return self.send_json({"ok": True, "workflows": list_workflows()})
        if path == "/api/workflows" and method == "POST":
            name = safe_name(body.get("name") or "未命名工作流")
            wid = body.get("id") or uuid.uuid4().hex[:10]
            wf = {"id": wid, "name": name, "api": body.get("api") or {},
                  "layout": body.get("layout") or {},
                  "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "created": body.get("created") or datetime.now().strftime("%Y-%m-%d %H:%M")}
            if body.get("builtin_copy"):
                wf["created"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            write_json_file(workflow_path(wid), wf)
            return self.send_json({"ok": True, "workflow": wf, "msg": f"已保存「{name}」"})
        if path == "/api/workflows/delete" and method == "POST":
            wid = body.get("id", "")
            p = workflow_path(wid)
            if os.path.exists(p):
                os.remove(p)
                return self.send_json({"ok": True, "msg": "已删除"})
            return self.send_json({"ok": False, "error": "内置工作流不可删除（或不存在）"}, 400)
        if path == "/api/convert" and method == "POST":
            try:
                oi = COMFY.object_info()
                api, warns = convert_ui_to_api(body.get("ui"), oi)
                return self.send_json({"ok": True, "api": api, "warnings": warns})
            except Exception as e:
                return self.send_json({"ok": False, "error": f"转换失败：{e}（需要 ComfyUI 在线）"})

        # ---- SSE
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            qsub = HUB.subscribe()
            try:
                hello = json.dumps({"type": "hello", "data": HUB.state}, ensure_ascii=False)
                self.wfile.write(f"data: {hello}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        ev = qsub.get(timeout=15)
                        self.wfile.write(b"data: " + json.dumps(ev, ensure_ascii=False).encode() + b"\n\n")
                        self.wfile.flush()
                    except queue_mod.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                HUB.unsubscribe(qsub)
            return

        # ---- Obsidian
        if path == "/api/obsidian/note":
            content = vault_note_content(q.get("path", ""))
            if content is None:
                return self.send_json({"ok": False, "error": "笔记不存在或路径非法"}, 404)
            return self.send_json({"ok": True, "content": content})
        if path == "/api/obsidian/vault":
            notes = vault_scan()
            week_ago = time.time() - 7 * 86400
            stats = {"count": len(notes),
                     "words": sum(n["words"] for n in notes),
                     "links": sum(len(n["links"]) for n in notes),
                     "recent7": sum(1 for n in notes if n["mtime"] >= week_ago)}
            return self.send_json({"ok": True, "notes": notes[:300], "stats": stats})
        if path == "/api/obsidian/status":
            return self.send_json({"ok": True, **obsidian_status()})
        if path == "/api/obsidian/archive" and method == "POST":
            r = archive_media(body.get("paths", []), title=body.get("title", ""),
                              note=body.get("note", ""), tags=body.get("tags"))
            return self.send_json(r)
        if path == "/api/obsidian/notes":
            _, notes_dir, _ = vault_dirs()
            notes = []
            if os.path.isdir(notes_dir):
                for fn in sorted(os.listdir(notes_dir), reverse=True):
                    if fn.endswith(".md"):
                        rel = os.path.relpath(os.path.join(notes_dir, fn), SETTINGS["vault_path"]).replace("\\", "/")
                        st = os.stat(os.path.join(notes_dir, fn))
                        notes.append({"file": rel, "mtime": int(st.st_mtime), "uri": obsidian_uri(rel)})
            return self.send_json({"ok": True, "notes": notes[:100]})
        if path == "/api/obsidian/archives":
            return self.send_json({"ok": True, "archives": read_json_file(ARCHIVE_LOG, [])})
        if path == "/api/obsidian/sync" and method == "POST":
            return self.send_json(sync_workflows_to_vault())
        if path == "/api/obsidian/open":
            rel = q.get("path", "")
            return self.send_json({"ok": True, "uri": obsidian_uri(rel)})

        if path == "/api/update/check":
            def _local_version():
                try:
                    return open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8").read().strip()
                except Exception:
                    return "0"
            local = _local_version()
            repo = SETTINGS.get("gitee_repo", "")
            token = SETTINGS.get("gitee_token", "")
            if not repo:
                return self.send_json({"ok": False, "error": "未配置 gitee_repo"})
            url = f"https://gitee.com/api/v5/repos/{repo}/releases/latest"
            if token:
                url += f"?access_token={token}"
            try:
                with urllib.request.urlopen(url, timeout=15) as r:
                    rel = json.loads(r.read())
                latest = (rel.get("tag_name") or "").lstrip("vV")
                newer = False
                try:
                    newer = tuple(int(x) for x in latest.split(".")) > tuple(int(x) for x in local.split("."))
                except Exception:
                    newer = latest != local
                return self.send_json({"ok": True, "local": local, "latest": latest, "newer": newer,
                                       "url": rel.get("html_url") or f"https://gitee.com/{repo}/releases",
                                       "notes": (rel.get("body") or "")[:500],
                                       "published": rel.get("published_at", "")})
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return self.send_json({"ok": False, "error": "仓库还没有 Release。发布方法：Gitee 仓库页 → 创建发行版 → 上传 ComfyAgent-win64.zip 附件，tag 填版本号（如 3.2.0）"})
                if e.code == 401:
                    return self.send_json({"ok": False, "error": "私有仓库需要在设置里配置 Gitee 私人令牌"})
                return self.send_json({"ok": False, "error": f"检查失败：HTTP {e.code}"})
            except Exception as e:
                return self.send_json({"ok": False, "error": f"检查失败：{e}"})

        # ---- 启动器
        if path == "/api/launcher/info":
            return self.send_json({"ok": True, **launcher_info()})
        if path == "/api/comfy/git":
            return self.send_json({"ok": True, **comfy_git_info()})
        if path == "/api/comfy/check_remote":
            return self.send_json(comfy_check_remote())
        if path == "/api/comfy/update" and method == "POST":
            return self.send_json(comfy_do_update())
        if path == "/api/comfy/launch" and method == "POST":
            return self.send_json(comfy_launch())
        if path == "/api/comfy/stop" and method == "POST":
            return self.send_json(comfy_stop())
        if path == "/api/comfy/restart" and method == "POST":
            stop = comfy_stop()
            if stop["ok"]:
                time.sleep(3)
            return self.send_json(comfy_launch())
        if path == "/api/comfy/log":
            try:
                logp = os.path.join(DATA_DIR, "comfy.log")
                with open(logp, encoding="utf-8", errors="replace") as f:
                    return self.send_json({"ok": True, "lines": "".join(f.readlines()[-300:]) or "（暂无日志）"})
            except Exception:
                return self.send_json({"ok": True, "lines": "（暂无日志：还没从创作台启动过 ComfyUI）"})

        if path == "/api/input_image" and method == "POST":
            name = copy_to_input(body.get("path", ""), tag=body.get("tag", "frame"))
            if name:
                return self.send_json({"ok": True, "input_name": name})
            return self.send_json({"ok": False, "error": "图片不存在或 ComfyUI input 目录无效"}, 400)
        # ---- 产线批次 / 角色库 / 拼接 / 备份
        if path == "/api/batches" and method == "GET":
            return self.send_json({"ok": True, "batches": _list_batches()})
        if path == "/api/batches/get" and method == "POST":
            b = _load_batch(body.get("id", ""))
            return self.send_json({"ok": bool(b), "batch": b}) if b else self.send_json({"ok": False, "error": "批次不存在"}, 404)
        if path == "/api/batches/save" and method == "POST":
            bid = body.get("id") or ("b" + datetime.now().strftime("%Y%m%d%H%M%S"))
            b = {"id": bid, "name": body.get("name") or bid,
                 "workflow_id": body.get("workflow_id") or "h3-t2v",
                 "created": body.get("created") or datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "items": body.get("items") or []}
            _save_batch(b)
            return self.send_json({"ok": True, "id": bid, "msg": "批次已保存"})
        if path == "/api/batches/delete" and method == "POST":
            p = _batch_path(body.get("id", ""))
            if os.path.exists(p):
                os.remove(p)
                return self.send_json({"ok": True, "msg": "已删除"})
            return self.send_json({"ok": False, "error": "不存在"}, 404)
        if path == "/api/batches/parse" and method == "POST":
            return self.send_json({"ok": True, "items": parse_script_text(body.get("text", ""))})
        if path == "/api/batches/run" and method == "POST":
            return self.send_json(run_batch(body.get("id", ""), draft=bool(body.get("draft"))))
        if path == "/api/batches/retry" and method == "POST":
            b = _load_batch(body.get("id", ""))
            idx = int(body.get("index", -1))
            if not b or idx < 0 or idx >= len(b.get("items", [])):
                return self.send_json({"ok": False, "error": "参数错误"}, 400)
            item = b["items"][idx]
            item["status"] = None
            _save_batch(b)
            b2 = run_batch(body.get("id", ""), only_index=idx)
            b = _load_batch(body.get("id", "")) or b
            return self.send_json({"ok": b2.get("ok", False), "msg": b2.get("msg", "已重新排队"), "batch": b})
        if path == "/api/batches/sync" and method == "POST":
            batch_sync_status()
            return self.send_json({"ok": True})
        if path == "/api/concat" and method == "POST":
            if not FFMPEG:
                return self.send_json({"ok": False, "error": "未找到 ffmpeg"})
            paths = [resolve_media(p) for p in (body.get("paths") or [])]
            paths = [p for p in paths if p and os.path.isfile(p)]
            if len(paths) < 2:
                return self.send_json({"ok": False, "error": "至少需要两段视频"})
            name = safe_name(body.get("name") or "成片") or "成片"
            outdir = os.path.join(SETTINGS["output_dir"], "成片")
            os.makedirs(outdir, exist_ok=True)
            out = os.path.join(outdir, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            lst = out + ".txt"
            with open(lst, "w", encoding="utf-8") as f:
                for p in paths:
                    f.write("file '" + p.replace("'", "'\\''") + "'\n")
            r = subprocess.run([FFMPEG, "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                                "-c", "copy", "-y", out], capture_output=True, text=True,
                               timeout=300, creationflags=0x08000000)
            if r.returncode != 0 or not os.path.isfile(out):
                r = subprocess.run([FFMPEG, "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                                    "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-y", out],
                                   capture_output=True, text=True, timeout=600, creationflags=0x08000000)
            os.remove(lst)
            # BGM 混音（可选）：背景音乐循环铺底后混合
            bgm = (body.get("bgm") or "").strip()
            bgm_vol = float(body.get("bgm_volume", 0.25))
            if bgm and os.path.isfile(bgm) and os.path.isfile(out):
                final = out.replace(".mp4", "_bgm.mp4")
                r2 = subprocess.run([FFMPEG, "-v", "error", "-i", out, "-stream_loop", "-1", "-i", bgm,
                                     "-filter_complex", f"[1:a]volume={bgm_vol}[b];[0:a][b]amix=inputs=2:duration=first[aout]",
                                     "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-y", final],
                                    capture_output=True, text=True, timeout=600, creationflags=0x08000000)
                if r2.returncode == 0 and os.path.isfile(final):
                    os.remove(out)
                    os.replace(final, out)
            if r.returncode == 0 and os.path.isfile(out):
                return self.send_json({"ok": True, "output": "成片/" + os.path.basename(out),
                                       "msg": f"已拼接 {len(paths)} 段 → {os.path.basename(out)}"})
            return self.send_json({"ok": False, "error": "拼接失败：" + (r.stderr or "")[-200:]})
        if path == "/api/video/last_frame" and method == "POST":
            # 镜头接龙：抽视频最后 1.5 秒内的末帧存入 output，供下一镜作 i2v 首帧
            if not FFMPEG:
                return self.send_json({"ok": False, "error": "未找到 ffmpeg"})
            rel = body.get("path", "")
            full = resolve_media(rel)
            if not full or not os.path.isfile(full):
                return self.send_json({"ok": False, "error": "视频不存在"})
            base = safe_name(os.path.splitext(os.path.basename(rel))[0])[:40] or "clip"
            out = os.path.join(SETTINGS.get("output_dir", BASE_DIR), base + "_lastframe.png")
            r = subprocess.run([FFMPEG, "-y", "-v", "error", "-sseof", "-1.5", "-i", full,
                                "-update", "1", "-frames:v", "1", out],
                               capture_output=True, text=True, timeout=60, creationflags=0x08000000)
            if not os.path.isfile(out) or os.path.getsize(out) == 0:
                return self.send_json({"ok": False, "error": "抽帧失败：" + (r.stderr or "")[-120:]})
            return self.send_json({"ok": True, "frame": os.path.basename(out)})
        if path == "/api/characters" and method == "GET":
            return self.send_json({"ok": True, "characters": list_characters()})
        if path == "/api/characters/save" and method == "POST":
            cid = body.get("id") or ("c" + datetime.now().strftime("%Y%m%d%H%M%S"))
            refs = [r for r in (body.get("refs") or []) if r]
            c = {"id": cid, "name": body.get("name") or cid,
                 "lock": body.get("lock", ""), "ref": refs[0] if refs else body.get("ref", ""),
                 "refs": refs,
                 "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
            write_text_atomic(_char_path(cid), json.dumps(c, ensure_ascii=False, indent=1))
            return self.send_json({"ok": True, "character": c, "msg": f"角色「{c['name']}」已保存"})
        if path == "/api/characters/delete" and method == "POST":
            p = _char_path(body.get("id", ""))
            if os.path.exists(p):
                os.remove(p)
                return self.send_json({"ok": True, "msg": "已删除"})
            return self.send_json({"ok": False, "error": "不存在"}, 404)
        if path == "/api/debug":
            import socket
            try:
                lan_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                lan_ip = ""
            return self.send_json({"ok": True, "DATA_DIR": DATA_DIR, "BASE_DIR": BASE_DIR,
                                   "STATIC_DIR": STATIC_DIR, "frozen": getattr(sys, "frozen", False),
                                   "cwd": os.getcwd(), "appdata_env": os.environ.get("APPDATA", ""),
                                   "lan_ip": lan_ip,
                                   "bind": "0.0.0.0" if SETTINGS.get("lan_access") else "127.0.0.1"})
        if path == "/api/backup" and method == "POST":
            return self.send_json({"ok": True, **backup_now(body.get("reason", "manual"))})
        if path == "/api/backups":
            bdir = os.path.join(DATA_DIR, "backups")
            files = sorted([f for f in os.listdir(bdir) if f.startswith("backup_")], reverse=True) if os.path.isdir(bdir) else []
            return self.send_json({"ok": True, "backups": files[:20]})
        # ---- 模板库
        if path == "/api/templates/preview":
            name = re.sub(r"[^A-Za-z0-9_.-]", "", q.get("name", ""))
            ext = "png" if q.get("ext", "webp") == "png" else "webp"
            rel = f"{name}-1.{ext}"
            data = None
            # 1) ComfyUI 本地 /templates/（模板包已下载时即时可用）
            try:
                with urllib.request.urlopen(COMFY.base + f"/templates/{rel}", timeout=15) as r:
                    data = r.read()
            except Exception:
                data = None
            # 2) 镜像链 + 24h 缓存
            if not data:
                try:
                    p = tpl_fetch(rel, timeout=25)
                    with open(p, "rb") as f:
                        data = f.read()
                except Exception:
                    data = None
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/webp")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return
        if path == "/api/templates/index":
            idx = tpl_index()
            if idx is None:
                return self.send_json({"ok": False, "error": "模板索引不可用（所有镜像均被阻断，稍后重试）"}, 502)
            return self.send_json({"ok": True, "groups": idx})
        if path == "/api/templates/file":
            try:
                p = tpl_fetch(q.get("name", ""))
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)}, 502)
            mime = ("image/webp" if p.endswith(".webp") else "image/png" if p.endswith(".png")
                    else "video/mp4" if p.endswith(".mp4") else "application/json")
            self.send_file(p, mime, ranges=self.headers.get("Range"))
            return
        if path == "/api/templates/workflow" and method == "POST":
            name = body.get("name", "")
            if not re.match(r"^[A-Za-z0-9_.-]+$", name):
                return self.send_json({"ok": False, "error": "非法模板名"}, 400)
            data = None
            # 首选：ComfyUI 服务器本地 /templates/ 路由（离线可用、零延迟）
            try:
                with urllib.request.urlopen(COMFY.base + f"/templates/{name}.json", timeout=20) as r:
                    data = json.loads(r.read())
            except Exception:
                data = None
            if data is None:
                # 兜底：镜像链拉取
                try:
                    p = tpl_fetch(name if name.endswith(".json") else name + ".json")
                    data = read_json_file(p, None)
                except Exception as e:
                    return self.send_json({"ok": False, "error": f"拉取失败：{e}"}, 502)
            if data is None:
                return self.send_json({"ok": False, "error": "模板 JSON 解析失败"}, 500)
            if "nodes" in data and COMFY.probe() is not None:
                try:
                    api_g, warns = convert_ui_to_api(data, COMFY.object_info())
                    return self.send_json({"ok": True, "format": "api", "api": api_g, "warnings": warns})
                except Exception as e:
                    return self.send_json({"ok": True, "format": "ui", "ui": data,
                                           "warnings": [f"自动转换失败（{e}），已返回 UI 原格式，请手动转换"]})
            return self.send_json({"ok": True, "format": "api", "api": data})

        if path == "/api/image_to_prompt" and method == "POST":
            return self.send_json(image_to_prompt(body.get("path", "")))
        # ---- 场景库 / 集数聚合 / 音频 / 字幕 / 风格归纳
        if path == "/api/scenes" and method == "GET":
            return self.send_json({"ok": True, "scenes": list_scenes()})
        if path == "/api/scenes/save" and method == "POST":
            sid = body.get("id") or ("s" + datetime.now().strftime("%Y%m%d%H%M%S"))
            s = {"id": sid, "name": body.get("name") or sid,
                 "desc": body.get("desc", ""), "tokens": body.get("tokens", ""),
                 "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
            write_text_atomic(os.path.join(SCENE_DIR, safe_name(sid) + ".json"),
                              json.dumps(s, ensure_ascii=False, indent=1))
            return self.send_json({"ok": True, "scene": s, "msg": "saved"})
        if path == "/api/scenes/delete" and method == "POST":
            fp = os.path.join(SCENE_DIR, safe_name(body.get("id", "")) + ".json")
            if os.path.isfile(fp):
                os.remove(fp)
                return self.send_json({"ok": True, "msg": "deleted"})
            return self.send_json({"ok": False, "error": "not found"}, 404)
        if path == "/api/batches/episodes":
            return self.send_json({"ok": True, "episodes": batch_episodes()})
        if path == "/api/audio_assets":
            return self.send_json({"ok": True, "audio": scan_audio_assets()[:100]})
        if path == "/api/style_induce" and method == "POST":
            return self.send_json(induce_style_from_images(body.get("paths", [])))
        if path == "/api/subtitle_burn" and method == "POST":
            if not FFMPEG:
                return self.send_json({"ok": False, "error": "ffmpeg not found"})
            video = resolve_media(body.get("video", ""))
            srt = body.get("srt_path", "")
            if not video or not os.path.isfile(video):
                return self.send_json({"ok": False, "error": "video not found"})
            if not srt or not os.path.isfile(srt):
                return self.send_json({"ok": False, "error": "srt not found"})
            base_n = os.path.splitext(video)[0]
            out = base_n + "_sub.mp4"
            srt_esc = srt.replace("\\", "/").replace(":", "\:").replace("'", "\'")
            r = subprocess.run([FFMPEG, "-v", "error", "-i", video,
                                "-vf", f"subtitles='{srt_esc}'",
                                "-c:a", "copy", "-y", out],
                               capture_output=True, text=True, timeout=600, creationflags=0x08000000)
            if r.returncode == 0 and os.path.isfile(out):
                return self.send_json({"ok": True, "output": os.path.basename(out)})
            return self.send_json({"ok": False, "error": (r.stderr or "")[-200:]})
        # ---- LLM 厂商
        if path == "/api/llm/providers":
            return self.send_json({"ok": True, "presets": [
                {"id": k, "name": v["name"], "base": v["base"], "models": v["models"]}
                for k, v in LLM_PRESETS.items()]})
        if path == "/api/llm/models" and method == "POST":
            ids = llm_models_fetch(body.get("provider", ""), body.get("base_url"), body.get("key"))
            preset = LLM_PRESETS.get(body.get("provider", ""), {})
            return self.send_json({"ok": ids is not None, "models": ids or preset.get("models", []),
                                   "fetched": ids is not None})
        # ---- Agent
        if path == "/api/styles":
            return self.send_json({"ok": True, "styles": [
                {"id": k, **{kk: vv for kk, vv in v.items()}} for k, v in STYLE_SOPS.items()]})
        if path == "/api/enhance_prompt" and method == "POST":
            return self.send_json(enhance_prompt(body.get("text", ""),
                                                 style_id=body.get("style"),
                                                 mode=body.get("mode", "image")))
        if path == "/api/agent" and method == "POST":
            return self.send_json({"ok": True, **agent_execute(body.get("text", ""))})

        return self.send_json({"ok": False, "error": "unknown endpoint " + path}, 404)


# ---------------------------------------------------------------- main

def _thumb_lru_cleanup(max_files=400):
    """缩略图缓存 LRU 清理：超过 max_files 删最旧的（迭代21）。"""
    try:
        files = [os.path.join(THUMB_DIR, f) for f in os.listdir(THUMB_DIR)]
        files = [f for f in files if os.path.isfile(f)]
        if len(files) > max_files:
            files.sort(key=os.path.getmtime)
            for f in files[:len(files) - max_files]:
                os.remove(f)
            print(f"* thumb LRU: cleaned {len(files) - max_files}")
    except Exception:
        pass


def create_server():
    """初始化配置/线程并返回 HTTPServer（供控制台模式和桌面壳共用）。"""
    global SETTINGS, COMFY
    ensure_dirs()
    # exe 旧版数据迁移：dist/ComfyAgent/data（随重建会被清空）→ APPDATA 永久数据目录
    if getattr(sys, "frozen", False):
        old = os.path.join(os.path.dirname(sys.executable), "data")
        if os.path.isdir(old):
            moved_marker = os.path.join(old, ".migrated")
            if not os.path.isfile(moved_marker):
                try:
                    for sub in ("workflows", "batches", "characters", "backups"):
                        src_d, dst_d = os.path.join(old, sub), os.path.join(DATA_DIR, sub)
                        if os.path.isdir(src_d):
                            os.makedirs(dst_d, exist_ok=True)
                            for f in os.listdir(src_d):
                                dp = os.path.join(dst_d, f)
                                if not os.path.exists(dp):
                                    shutil.copy2(os.path.join(src_d, f), dp)
                    for f in ("settings.json", "runs.json", "templates_index.json"):
                        sf, df = os.path.join(old, f), os.path.join(DATA_DIR, f)
                        if os.path.isfile(sf) and not os.path.exists(df):
                            shutil.copy2(sf, df)
                    open(moved_marker, "w").write("migrated")
                    print("* migrated old dist data ->", DATA_DIR)
                except Exception as e:
                    print("* migrate warn:", e)
        # 首次安装种子：exe 旁 seed/ 目录（构建时附带内置工作流/角色示例）
        seed_wf = os.path.join(BASE_DIR, "seed", "workflows")
        wf_dir = os.path.join(DATA_DIR, "workflows")
        os.makedirs(wf_dir, exist_ok=True)
        if os.path.isdir(seed_wf):
            for f in os.listdir(seed_wf):
                if f.endswith(".json") and not os.path.exists(os.path.join(wf_dir, f)):
                    shutil.copy2(os.path.join(seed_wf, f), os.path.join(wf_dir, f))
            print("* seeded builtin workflows")
    SETTINGS = load_settings()
    COMFY = ComfyClient(SETTINGS["comfy_url"])
    threading.Thread(target=ws_monitor_loop, daemon=True).start()
    threading.Thread(target=queue_poll_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop, daemon=True).start()
    threading.Thread(target=lambda: (time.sleep(6), _thumb_lru_cleanup(), backup_now("startup")), daemon=True).start()
    port = int(SETTINGS.get("port", 8190))
    bind = "0.0.0.0" if SETTINGS.get("lan_access") else "127.0.0.1"
    httpd = ThreadingHTTPServer((bind, port), Handler)
    httpd.daemon_threads = True
    print(f"* ComfyAgent running at http://127.0.0.1:{port}  (ComfyUI: {SETTINGS['comfy_url']})")
    print(f"* gallery root: {SETTINGS['output_dir']}")
    print(f"* obsidian vault: {SETTINGS['vault_path']}")
    # exe 双击启动 / 带 --open 参数时自动打开浏览器（桌面壳模式不走这里）
    if not getattr(sys, "frozen", False) or "--open" in sys.argv:
        if "--open" in sys.argv:
            threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    return httpd


def main():
    httpd = create_server()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
