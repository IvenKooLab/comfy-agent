"""集成验证：/api/upload_media 透传到 mock ComfyUI 的 /upload/image。
起 mock(8189) + 临时 ComfyAgent server 实例(8191)，发 multipart 断言转发完整性。"""
import http.server, json, os, shutil, subprocess, sys, time, urllib.request, threading

ROOT = r"E:/work/gitee/comfy-agent"
TMP = os.path.join(os.environ.get("TEMP", "/tmp"), "ca_upload_test")
MOCK_PORT, SRV_PORT = 8189, 8191
received = {}

class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b"{}")
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        received["ct"] = self.headers.get("Content-Type", "")
        received["len"] = len(body)
        received["path"] = self.path
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"name": "uploaded.mp4", "subfolder": "", "type": "input"}).encode())

def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(os.path.join(TMP, "data"), exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(TMP, "static"))
    shutil.copy(os.path.join(ROOT, "server.py"), os.path.join(TMP, "server.py"))
    with open(os.path.join(TMP, "data", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"port": SRV_PORT, "comfy_url": f"http://127.0.0.1:{MOCK_PORT}"}, f)

    mock = http.server.ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), Mock)
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{SRV_PORT}"
        for _ in range(40):
            try:
                urllib.request.urlopen(base + "/api/status", timeout=2); break
            except Exception:
                time.sleep(0.5)
        # 构造 multipart（手写 boundary，模拟浏览器 FormData）
        boundary = "----caTestBoundary123"
        payload = b"\xff" * 4096  # 模拟二进制视频块
        mp = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"drive.mp4\"\r\n"
              f"Content-Type: video/mp4\r\n\r\n").encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(base + "/api/upload_media", data=mp, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        assert resp == {"name": "uploaded.mp4", "subfolder": "", "type": "input"}, resp
        assert received["len"] == len(mp), (received["len"], len(mp))
        assert "boundary=----caTestBoundary123" in received["ct"], received["ct"]
        assert received["path"] == "/upload/image?type=input&overwrite=true", received["path"]
        print("PASS: 透传完整（%d bytes, boundary ok, 返回 name 正确）" % received["len"])
    finally:
        srv.terminate()
        mock.shutdown()

if __name__ == "__main__":
    main()
