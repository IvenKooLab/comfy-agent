# -*- coding: utf-8 -*-
"""出片前门禁回归测试：七段式校验 / 可拍性 linter / 首尾帧检查 / FL2V 工作流路由 /
定向注图 / 复盘。运行：python -m unittest tests.test_pipeline_gate"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


FLF2V = next(w for w in server.list_workflows() if w.get("id") == "h3-flf2v")
I2V = next(w for w in server.list_workflows() if w.get("id") == "h3-i2v")


class TestPromptStructure(unittest.TestCase):
    def test_missing_sections_reported(self):
        item = {"prompt": "【画风】写实\n【镜头】4 秒 中景 平视 不推不拉"}
        pre = server.precheck_shot(item, I2V)
        codes = [w["code"] for w in pre["warns"]]
        self.assertIn("PROMPT_SECTIONS_MISSING", codes)
        msg = next(w["msg"] for w in pre["warns"] if w["code"] == "PROMPT_SECTIONS_MISSING")
        for sec in ("构图", "人物", "逐秒", "声音", "约束"):
            self.assertIn(sec, msg)

    def test_full_sections_pass(self):
        item = {"prompt": "【画风】写实\n【镜头】4 秒 中景 平视\n【构图与配色】左侧\n【人物】白衣剑客\n"
                         "【逐秒】0–4 秒 走过去\n【声音】只有脚步声\n【约束】一镜到底，无文字"}
        pre = server.precheck_shot(item, I2V)
        self.assertFalse([w for w in pre["warns"] if w["code"] == "PROMPT_SECTIONS_MISSING"])
        self.assertTrue(pre["ok"])

    def test_negation_flagged(self):
        item = {"prompt": "【画风】写实。" * 2 + "不要出现文字，别让壶出水"}
        pre = server.precheck_shot(item, I2V)
        self.assertIn("PROMPT_NEGATION", [w["code"] for w in pre["warns"]])

    def test_filmability_hits(self):
        item = {"prompt": "女孩手里拿着一个杯子，招牌上写着再见，镜子里有倒影"}
        pre = server.precheck_shot(item, I2V)
        msgs = [w["msg"] for w in pre["warns"] if w["code"] == "FILMABILITY"]
        self.assertGreaterEqual(len(msgs), 1)
        self.assertTrue(any("文字" in m for m in msgs))


class TestFrameChecks(unittest.TestCase):
    def test_last_without_first_blocks(self):
        pre = server.precheck_shot({"prompt": "x" * 30, "last_frame": "lf.png"}, FLF2V)
        self.assertFalse(pre["ok"])
        self.assertIn("FRAME_FIRST_MISSING", [f["code"] for f in pre["fails"]])

    def test_last_on_unsupported_workflow_blocks(self):
        pre = server.precheck_shot({"prompt": "x" * 30, "first_frame": "a.png", "last_frame": "b.png"}, I2V)
        self.assertIn("WF_NO_LASTFRAME", [f["code"] for f in pre["fails"]])

    def test_size_mismatch_blocks(self):
        with patch.object(server, "_ffprobe_size", side_effect=[(1024, 1024), (1280, 720)]), \
             patch.object(server, "_frame_ssim", return_value=0.9):
            pre = server.precheck_shot({"prompt": "x" * 30, "first_frame": "a.png", "last_frame": "b.png"}, FLF2V)
        self.assertIn("FRAME_SIZE_MISMATCH", [f["code"] for f in pre["fails"]])

    def test_ssim_drift_and_identical(self):
        with patch.object(server, "_ffprobe_size", return_value=(1024, 1024)):
            with patch.object(server, "_frame_ssim", return_value=0.3):
                pre = server.precheck_shot({"prompt": "x" * 30, "first_frame": "a", "last_frame": "b"}, FLF2V)
                self.assertIn("FRAME_LAYOUT_DRIFT", [w["code"] for w in pre["warns"]])
            with patch.object(server, "_frame_ssim", return_value=0.999):
                pre = server.precheck_shot({"prompt": "x" * 30, "first_frame": "a", "last_frame": "b"}, FLF2V)
                self.assertIn("FRAME_IDENTICAL", [w["code"] for w in pre["warns"]])

    def test_char_lock_warning(self):
        pre = server.precheck_shot({"prompt": "x" * 40}, I2V, lock="白衣剑客，黑发")
        self.assertIn("CHAR_LOCK_MISSING", [w["code"] for w in pre["warns"]])


class TestFlf2vRouting(unittest.TestCase):
    def test_auto_upgrade_to_flf2v(self):
        wf, upgraded = server.resolve_shot_workflow({"last_frame": "x.png"}, I2V)
        self.assertTrue(upgraded)
        self.assertEqual(wf["id"], "h3-flf2v")

    def test_no_upgrade_without_last_frame(self):
        wf, upgraded = server.resolve_shot_workflow({}, I2V)
        self.assertFalse(upgraded)
        self.assertEqual(wf["id"], "h3-i2v")

    def test_image_map_targets_two_loaders(self):
        m = server._image_map_for(FLF2V, "ff.png", "lf.png")
        self.assertEqual(m, {"20": "ff.png", "21": "lf.png"})
        # 只给首帧时不该写尾帧节点
        self.assertEqual(server._image_map_for(FLF2V, "ff.png", None), {"20": "ff.png"})

    def test_workflow_has_last_frame_input(self):
        self.assertTrue(server.wf_supports(FLF2V, "last_frame"))
        self.assertFalse(server.wf_supports(I2V, "last_frame"))


class TestSubmitImageMap(unittest.TestCase):
    def test_map_overrides_specific_loaders(self):
        captured = {}

        class C:
            def probe(self):
                return {"devices": [{"vram_total": 1 << 30}]}

            def http(self, path, payload=None, timeout=None):
                captured.update(payload["prompt"])
                return {"prompt_id": "p1"}
        with patch.object(server, "COMFY", C()), patch.object(server, "add_run", lambda *a, **k: None), \
             patch.object(server, "SETTINGS", {"client_id": "t"}):
            server.submit_workflow({"name": "t", "api": FLF2V["api"]}, times=1,
                                   overrides={"text": "hi", "__image_map__": {"20": "ff.png", "21": "lf.png"}})
        self.assertEqual(captured["20"]["inputs"]["image"], "ff.png")
        self.assertEqual(captured["21"]["inputs"]["image"], "lf.png")

    def test_legacy_single_image_not_clobbering_mapped(self):
        captured = {}

        class C:
            def probe(self):
                return {"devices": [{"vram_total": 1 << 30}]}

            def http(self, path, payload=None, timeout=None):
                captured.update(payload["prompt"])
                return {"prompt_id": "p1"}
        with patch.object(server, "COMFY", C()), patch.object(server, "add_run", lambda *a, **k: None), \
             patch.object(server, "SETTINGS", {"client_id": "t"}):
            server.submit_workflow({"name": "t", "api": FLF2V["api"]}, times=1,
                                   overrides={"text": "hi", "__image__": "both.png",
                                              "__image_map__": {"21": "lf.png"}})
        # 20 走整体注入，21 保持定向值
        self.assertEqual(captured["20"]["inputs"]["image"], "both.png")
        self.assertEqual(captured["21"]["inputs"]["image"], "lf.png")


class TestRetro(unittest.TestCase):
    def test_retro_written(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, patch.object(server, "RETRO_DIR", d):
            b = {"name": "E01 测试集", "gpu_min": 42, "items": [
                {"name": "S1", "status": "success", "precheck": {"warns": [{"code": "FILMABILITY"}]}},
                {"name": "S2", "status": "blocked", "precheck": {"fails": [{"code": "FRAME_SIZE_MISMATCH"}]}},
                {"name": "S3", "status": "success", "audit": {"verdict": "通过"}},
            ]}
            r = server.retro_batch(b)
            self.assertTrue(r["ok"])
            body = open(r["path"], encoding="utf-8").read()
            self.assertIn("E01 测试集", body)
            self.assertIn("FRAME_SIZE_MISMATCH", body)
            self.assertIn("通过 1", body.replace("，", " "))


if __name__ == "__main__":
    unittest.main()
