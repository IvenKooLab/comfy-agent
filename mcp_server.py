#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ComfyAgent MCP Server（stdio 传输，零依赖，纯标准库）

任何 MCP host（ZCode / Claude Desktop / Cursor 等）通过 stdio 拉起本进程，
转调本机 ComfyAgent HTTP API（默认 127.0.0.1:8190，可用环境变量 COMFYAGENT_URL 覆盖）。

配置示例（mcpServers 片段）：
  "comfyagent": {
    "command": "python",
    "args": ["E:/work/gitee/comfy-agent/mcp_server.py"],
    "env": { "COMFYAGENT_URL": "http://127.0.0.1:8190" }
  }

协议：MCP over stdio（newline-delimited JSON-RPC 2.0），支持
  initialize / notifications/initialized / ping / tools/list / tools/call
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("COMFYAGENT_URL", "http://127.0.0.1:8190").rstrip("/")
VERSION = "1.5.1"
PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "query_status",
        "description": "查询 ComfyUI 与 ComfyAgent 状态：在线与否、正在执行/排队任务数、GPU 显存占用。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_generation",
        "description": ("提交生成任务到 ComfyUI（占用 GPU）。mode=image 走 Flux 文生图（中文自动增强为英文），"
                        "mode=video 走 H3 文生视频（约 4.7 分钟/条）。仅当用户明确要求生成时调用，count≤4。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "画面描述，中文或英文"},
                "mode": {"type": "string", "enum": ["image", "video"], "default": "image"},
                "count": {"type": "integer", "default": 1, "maximum": 4},
                "seed": {"type": "integer", "description": "随机种子，缺省随机"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "list_workflows",
        "description": "列出可用工作流（含 tier 档位：final=成片可复现 / draft=草稿快跑不可复现，及预估耗时）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_gallery",
        "description": "按关键词搜索本地画廊（output 目录）成果文件，返回文件名/类型/相对路径。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "文件名关键词，空串=最新"},
                "limit": {"type": "integer", "default": 8, "maximum": 20},
            },
            "required": ["query"],
        },
    },
]


def http(path, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_tool(name, args):
    """执行工具，返回 (text, is_error)。"""
    if name == "query_status":
        st = http("/api/status")
        q = {}
        try:
            q = http("/api/queue").get("queue") or {}
        except Exception:
            pass
        txt = (f"ComfyAgent online ({st.get('version', '?')}); ComfyUI {'online' if st.get('comfy_online') else 'OFFLINE'}; "
               f"running={len(q.get('queue_running', []))} pending={len(q.get('queue_pending', []))}")
        return txt, False
    if name == "submit_generation":
        r = http("/api/generate", {"prompt": args.get("prompt", ""), "mode": args.get("mode", "image"),
                                   "count": args.get("count", 1), "seed": args.get("seed")})
        is_err = not r.get("ok")
        return json.dumps(r, ensure_ascii=False), is_err
    if name == "list_workflows":
        r = http("/api/workflows")
        wfs = r.get("workflows") or []
        lines = [f"{w.get('name')} (id={w.get('id')}, tier={w.get('tier', '-')}, ~{w.get('est_min', '?')}min)"
                 for w in wfs]
        return "\n".join(lines) or "(no workflows)", False
    if name == "search_gallery":
        q = (args.get("query") or "").lower()
        limit = max(1, min(int(args.get("limit") or 8), 20))
        items = http("/api/gallery").get("items") or []
        if q:
            items = [i for i in items if q in i.get("name", "").lower() or q in i.get("path", "").lower()]
        if not items:
            return "no results", False
        return "\n".join(f"{i.get('name')} | {'video' if i.get('kind') == 'video' else 'image'} | {i.get('path')}"
                         for i in items[:limit]), False
    return f"unknown tool: {name}", True


def rpc_result(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(msg):
    """处理一条 JSON-RPC 消息，返回应答 dict 或 None（notification 无应答）。"""
    method = msg.get("method", "")
    rid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return rpc_result(rid, {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "comfyagent", "version": VERSION},
        })
    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None
    if method == "ping":
        return rpc_result(rid, {})
    if method == "tools/list":
        return rpc_result(rid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            text, is_err = call_tool(name, args)
            return rpc_result(rid, {"content": [{"type": "text", "text": text}], "isError": is_err})
        except Exception as e:
            return rpc_result(rid, {"content": [{"type": "text", "text": f"tool error: {e}"}], "isError": True})
    if rid is not None:
        return rpc_error(rid, -32601, f"method not found: {method}")
    return None


def main():
    # stdio 循环：每行一条 JSON-RPC 消息；日志走 stderr（stdout 是协议通道，严禁污染）
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            resp = rpc_error(msg.get("id"), -32603, f"internal error: {e}")
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
