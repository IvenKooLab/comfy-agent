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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
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
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


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


def list_workflows():
    out = list(BUILTIN_WORKFLOWS.values())
    for fn in os.listdir(WORKFLOW_DIR):
        if fn.endswith(".json"):
            wf = read_json_file(os.path.join(WORKFLOW_DIR, fn), None)
            if wf:
                out.append(wf)
    out.sort(key=lambda w: (w.get("builtin", False) is False, w.get("name", "")))
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


# ---------------------------------------------------------------- agent (rules)

def zhipu_chat(text, key, model):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": (
                "你是 ComfyAgent 控制台助手，把用户中文指令转成 JSON 动作。可用动作："
                '{"run":{"workflow":"名称","times":1,"seed":null,"text":"提示词覆盖"},'
                '{"interrupt":{}},{"clear_queue":{}},{"status":{}},'
                '{"archive":{"count":5,"title":""}},{"open":{"view":"gallery"}}。'
                "只输出一个 JSON 对象，不要多余文字。无法理解则输出 {\"reply\":\"解释原因\"}")},
            {"role": "user", "content": text},
        ], "temperature": 0.1,
    }).encode()
    req = urllib.request.Request("https://open.bigmodel.cn/api/paas/v4/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


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
        wf = BUILTIN_WORKFLOWS["Flux 文生图（内置）"]
        overrides = {"text": prompt_text}
        if size:
            overrides.update({"width": size[0], "height": size[1]})
        res = submit_workflow(wf, times=1, seed=None, overrides=overrides)
        reply = res.get("msg", "")
        acts.append({"type": "submitted", "prompt_ids": res.get("prompt_ids", [])})
    else:
        if SETTINGS.get("zhipu_key"):
            try:
                raw = zhipu_chat(t, SETTINGS["zhipu_key"], SETTINGS.get("zhipu_model", "glm-4-flash"))
                raw = raw.strip().strip("`")
                raw = re.sub(r"^json\s*", "", raw)
                obj = json.loads(raw)
                if "reply" in obj and len(obj) == 1:
                    reply = obj["reply"]
                else:
                    return agent_execute_coerce(obj)
            except Exception as e:
                reply = f"（GLM 解析失败：{e}）" + AGENT_HELP
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

def submit_workflow(wf, times=1, seed=None, overrides=None):
    """提交工作流到 ComfyUI，返回 {ok, msg, prompt_ids}。支持批量变 seed 与参数覆盖。"""
    api = json.loads(json.dumps(wf.get("api", {})))  # deep copy
    if not api:
        return {"ok": False, "msg": "工作流为空"}
    if overrides:
        applied = 0
        for nid, node in api.items():
            ins = node.get("inputs", {})
            for k, v in overrides.items():
                if k in ins and isinstance(ins[k], (str, int, float)):
                    ins[k] = v
                    applied += 1
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
                     "submitted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "queued"})
        n = len(prompt_ids)
        msg = f"已提交「{wf.get('name')}」×{n}（seed=" + (
            str(seed) if seed is not None else "随机") + "），到「任务」页看进度。"
        return {"ok": True, "msg": msg, "prompt_ids": prompt_ids}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return {"ok": False, "msg": f"ComfyUI 拒绝（{e.code}）：{detail}"}
    except Exception as e:
        return {"ok": False, "msg": f"提交失败：{e}（ComfyUI 在线吗？）"}


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
            s.pop("zhipu_key", None)
            s.pop("client_id", None)
            return self.send_json({"ok": True, "settings": s})
        if path == "/api/settings" and method == "POST":
            for k in ("port", "comfy_url", "output_dir", "vault_path", "zhipu_model"):
                if k in body:
                    SETTINGS[k] = body[k]
            if body.get("zhipu_key"):
                SETTINGS["zhipu_key"] = body["zhipu_key"]
            save_settings(SETTINGS)
            _gallery_cache["ts"] = 0
            return self.send_json({"ok": True, "msg": "已保存（端口改动需重启服务）"})

        if path == "/api/status":
            st = COMFY.probe()
            gal = scan_gallery()
            return self.send_json({"ok": True, "comfy_online": st is not None, "system_stats": st,
                                   "media_count": len(gal), "latest_mtime": gal[0]["mtime"] if gal else 0,
                                   "ws_state": HUB.state, "ffmpeg": bool(FFMPEG)})

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
                                  seed=body.get("seed"), overrides=body.get("overrides"))
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

        # ---- Agent
        if path == "/api/agent" and method == "POST":
            return self.send_json({"ok": True, **agent_execute(body.get("text", ""))})

        return self.send_json({"ok": False, "error": "unknown endpoint " + path}, 404)


# ---------------------------------------------------------------- main

def main():
    global SETTINGS, COMFY
    ensure_dirs()
    SETTINGS = load_settings()
    COMFY = ComfyClient(SETTINGS["comfy_url"])
    threading.Thread(target=ws_monitor_loop, daemon=True).start()
    threading.Thread(target=queue_poll_loop, daemon=True).start()
    port = int(SETTINGS.get("port", 8190))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    print(f"* ComfyAgent running at http://127.0.0.1:{port}  (ComfyUI: {SETTINGS['comfy_url']})")
    print(f"* gallery root: {SETTINGS['output_dir']}")
    print(f"* obsidian vault: {SETTINGS['vault_path']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
