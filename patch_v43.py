# -*- coding: utf-8 -*-
"""v4.3 server round-2 patch: BGM/refs/image_to_prompt/multi-step/LAN"""
import sys

p = 'server.py'
src = open(p, encoding='utf-8').read()
ok = []

def rep(anchor, new, tag):
    global src
    if anchor in src:
        src = src.replace(anchor, new, 1)
        ok.append(tag)
    else:
        print('MISS:', tag)

# E) concat BGM
rep('''            os.remove(lst)
            # BGM 混音（可选）：背景音乐循环铺底，音量可调''',
'''            os.remove(lst)
            # BGM 混音（可选）：背景音乐循环铺底，音量可调''', 'E-anchor-check')

old = '''            if r.returncode != 0 or not os.path.isfile(out):
                r = subprocess.run([FFMPEG, "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                                    "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-y", out],
                                   capture_output=True, text=True, timeout=600, creationflags=0x08000000)
            os.remove(lst)'''
new = '''            if r.returncode != 0 or not os.path.isfile(out):
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
                    os.replace(final, out)'''
rep(old, new, 'E-bgm')

# F) characters refs[]
old = '''        if path == "/api/characters/save" and method == "POST":
            cid = body.get("id") or ("c" + datetime.now().strftime("%Y%m%d%H%M%S"))
            c = {"id": cid, "name": body.get("name") or cid,
                 "lock": body.get("lock", ""), "ref": body.get("ref", ""),
                 "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}'''
new = '''        if path == "/api/characters/save" and method == "POST":
            cid = body.get("id") or ("c" + datetime.now().strftime("%Y%m%d%H%M%S"))
            refs = [r for r in (body.get("refs") or []) if r]
            c = {"id": cid, "name": body.get("name") or cid,
                 "lock": body.get("lock", ""), "ref": refs[0] if refs else body.get("ref", ""),
                 "refs": refs,
                 "updated": datetime.now().strftime("%Y-%m-%d %H:%M")}'''
rep(old, new, 'F-refs')

# G) image_to_prompt function + route
old = 'def _llm_chat(messages, temperature=0.3, timeout=60):'
new = '''def image_to_prompt(path):
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


def _llm_chat(messages, temperature=0.3, timeout=60):'''
rep(old, new, 'G-func')

old = '''        # ---- LLM 厂商'''
new = '''        if path == "/api/image_to_prompt" and method == "POST":
            return self.send_json(image_to_prompt(body.get("path", "")))
        # ---- LLM 厂商'''
rep(old, new, 'G-route')

# H) 助手多步
old = '''            "你是 ComfyAgent 控制台助手，把用户中文指令转成 JSON 动作。可用动作："'''
new = '''            "你是 ComfyAgent 控制台助手，把用户中文指令转成 JSON 动作。单个动作用单个对象；需要多步时输出 {\\"actions\\":[动作1,动作2]}。可用动作："'''
rep(old, new, 'H1')

old = '''                obj = json.loads(raw)
                if "reply" in obj and len(obj) == 1:
                    reply = obj["reply"]
                else:
                    return agent_execute_coerce(obj)'''
new = '''                obj = json.loads(raw)
                if "reply" in obj and len(obj) == 1:
                    reply = obj["reply"]
                elif "actions" in obj and isinstance(obj["actions"], list):
                    parts, acts = [], []
                    for a in obj["actions"][:6]:
                        r2 = agent_execute_coerce(a)
                        parts.append(r2.get("reply", ""))
                        acts.extend(r2.get("actions", []))
                    reply = "\\n".join(p for p in parts if p) or "已完成全部动作"
                    return {"reply": reply, "actions": acts}
                else:
                    return agent_execute_coerce(obj)'''
rep(old, new, 'H2')

# I) LAN bind
old = '''    port = int(SETTINGS.get("port", 8190))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)'''
new = '''    port = int(SETTINGS.get("port", 8190))
    bind = "0.0.0.0" if SETTINGS.get("lan_access") else "127.0.0.1"
    httpd = ThreadingHTTPServer((bind, port), Handler)'''
rep(old, new, 'I-bind')

# J) debug lan_ip + whitelist
old = '''            return self.send_json({"ok": True, "DATA_DIR": DATA_DIR, "BASE_DIR": BASE_DIR,
                                   "STATIC_DIR": STATIC_DIR, "frozen": getattr(sys, "frozen", False),
                                   "cwd": os.getcwd(), "appdata_env": os.environ.get("APPDATA", "")})'''
new = '''            import socket
            try:
                lan_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                lan_ip = ""
            return self.send_json({"ok": True, "DATA_DIR": DATA_DIR, "BASE_DIR": BASE_DIR,
                                   "STATIC_DIR": STATIC_DIR, "frozen": getattr(sys, "frozen", False),
                                   "cwd": os.getcwd(), "appdata_env": os.environ.get("APPDATA", ""),
                                   "lan_ip": lan_ip,
                                   "bind": "0.0.0.0" if SETTINGS.get("lan_access") else "127.0.0.1"})'''
rep(old, new, 'J-debug')

old = '''                      "comfy_watchdog", "comfy_autorequeue"):'''
new = '''                      "comfy_watchdog", "comfy_autorequeue", "batch_auto_retry", "lan_access"):'''
rep(old, new, 'J-wl')

open(p, 'w', encoding='utf-8', newline='\n').write(src)
print('APPLIED:', len(ok), '|', ', '.join(ok))
