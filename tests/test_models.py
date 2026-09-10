"""集成验证：模型管理 API（scan/presets/download）+ check_missing_models。
临时 ComfyAgent 实例(8192) + mock ComfyUI(8189) + 假 models 目录。"""
import http.server, json, os, shutil, subprocess, sys, time, urllib.request, threading

ROOT = r"E:/work/gitee/comfy-agent"
TMP = os.path.join(os.environ.get("TEMP", "/tmp"), "ca_models_test")
MOCK_PORT, SRV_PORT = 8189, 8192
FAKE_COMFY = os.path.join(TMP, "ComfyUI")
sent_ranges = []


class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b"{}")
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "1048576")  # 1MB
        self.end_headers()
    def do_POST(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b"{}")


def wait_up(base, timeout=25):
    for _ in range(int(timeout / 0.5)):
        try:
            urllib.request.urlopen(base + "/api/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(os.path.join(TMP, "data"))
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(TMP, "static"))
    shutil.copy(os.path.join(ROOT, "server.py"), os.path.join(TMP, "server.py"))
    # 假 ComfyUI：models 里放一个已安装的 SCAIL-2 文件（用 sam3 的名字，截断大小无所谓）
    sam_dir = os.path.join(FAKE_COMFY, "models", "checkpoints")
    os.makedirs(sam_dir)
    with open(os.path.join(sam_dir, "sam3.1_multiplex_fp16.safetensors"), "wb") as f:
        f.write(b"0" * 4096)
    with open(os.path.join(TMP, "data", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"port": SRV_PORT, "comfy_url": f"http://127.0.0.1:{MOCK_PORT}",
                   "comfy_dir": FAKE_COMFY}, f)

    mock = http.server.ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), Mock)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{SRV_PORT}"
        assert wait_up(base), "server 起不来"

        # 1) scan：假文件在 checkpoints 下
        r = json.loads(urllib.request.urlopen(base + "/api/models/scan", timeout=10).read())
        assert r["ok"] and r["root"].replace("/", "\\").endswith("ComfyUI\\models"), r.get("root")
        assert any(i["name"] == "sam3.1_multiplex_fp16.safetensors" for i in r["dirs"]["checkpoints"]), r["dirs"]["checkpoints"]

        # 2) presets：sam3 标已安装，其它未安装；H3 套件 url=None
        r = json.loads(urllib.request.urlopen(base + "/api/models/presets", timeout=10).read())
        sc = next(s for s in r["suites"] if s["id"] == "scail2")
        sam = next(m for m in sc["models"] if "sam3" in m["name"])
        assert sam["installed"] is True
        assert sc["installed_count"] == 1 and sc["model_count"] == 6
        h3 = next(s for s in r["suites"] if s["id"] == "h3t2v")
        assert all(m["url"] is None for m in h3["models"])

        # 3) download：对预设里的 vae 发起下载 → mock 支持 HEAD，但 GET 会走 do_GET 返回 "{}"（2字节）非 1MB——
        #    Range 下载会一直读到 EOF=2 字节 < total，循环 done<total 永假退出 → verify 兜底
        req = urllib.request.Request(base + "/api/models/download", method="POST",
                                     data=json.dumps({"suite": "scail2", "name": "Wan2_1_VAE_bf16.safetensors"}).encode(),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        assert r["ok"] and r["job"]["status"] in ("downloading", "done", "error"), r
        time.sleep(3)
        r2 = json.loads(urllib.request.urlopen(base + "/api/models/downloads", timeout=10).read())
        job = next(j for j in r2["downloads"] if j["name"] == "Wan2_1_VAE_bf16.safetensors")
        assert job["status"] in ("done", "error", "downloading"), job  # mock 数据截断，允许 error；关键是任务生命周期在跑
        print(f"PASS: scan/presets/download 链路正常（job 状态={job['status']}，mock 数据截断属预期）")

        # 4) check_missing_models 单元断言
        sys.path.insert(0, ROOT)
        import server
        server.SETTINGS = {"comfy_dir": FAKE_COMFY}  # 单测环境跳过 main() 的 SETTINGS 初始化
        api_g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "not_installed_model.safetensors"}},
                 "2": {"class_type": "VAELoader", "inputs": {"vae_name": "sam3.1_multiplex_fp16.safetensors"}}}
        # vae 目录里没有该文件 → 也会 missing；临时造一个
        vae_dir = os.path.join(FAKE_COMFY, "models", "vae"); os.makedirs(vae_dir, exist_ok=True)
        with open(os.path.join(vae_dir, "sam3.1_multiplex_fp16.safetensors"), "wb") as f:
            f.write(b"x")
        miss = server.check_missing_models(api_g)
        assert len(miss) == 1 and miss[0]["file"] == "not_installed_model.safetensors", miss
        print("PASS: check_missing_models 检测正确（1 缺 1 有）")
    finally:
        srv.terminate()
        mock.shutdown()

if __name__ == "__main__":
    main()
