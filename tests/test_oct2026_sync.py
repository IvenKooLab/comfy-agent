# -*- coding: utf-8 -*-
"""v1.6.0 十月生态同步回归测试：MOSS-Image / FLUX 3 Klein 内置工作流结构、
模型套件清单、text 覆盖只写首个文本节点。运行：python -m unittest tests.test_oct2026_sync"""
import unittest
import sys, os
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server


MOSS_WF = server.BUILTIN_WORKFLOWS["MOSS-Image 文生图（内置）"]
KLEIN_WF = server.BUILTIN_WORKFLOWS["FLUX 3 Klein 文生图（内置）"]


def _link_targets(api):
    """校验执行图连线完整性：所有 ["节点id", 槽] 引用必须存在。返回 {节点id: {输入名: 源节点id}}。"""
    refs = {}
    for nid, node in api.items():
        for k, v in node["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in api:
                refs.setdefault(nid, {})[k] = str(v[0])
            elif isinstance(v, list) and len(v) == 2:
                raise AssertionError(f"{nid}.{k} 引用了不存在的节点 {v[0]}")
    return refs


class TestNewBuiltinWorkflows(unittest.TestCase):
    def test_registered_and_unique(self):
        ids = [w.get("id") for w in server.BUILTIN_WORKFLOWS.values()]
        self.assertIn("builtin-moss", ids)
        self.assertIn("builtin-klein", ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_link_integrity(self):
        for wf in (MOSS_WF, KLEIN_WF):
            _link_targets(wf["api"])  # 引用不存在节点时直接抛 AssertionError

    def test_moss_structure_matches_official_template(self):
        api = MOSS_WF["api"]
        types = [n["class_type"] for n in api.values()]
        # 官方 image_moss_image_t2i 关键节点：UNETLoader + CLIPLoader(moss_image) + 双 CLIPTextEncode
        # + SkipLayerGuidanceDiTSimple + EmptyFlux2LatentImage + KSampler(er_sde) + VAELoader + SaveImage
        self.assertEqual(types.count("UNETLoader"), 1)
        self.assertEqual(types.count("CLIPLoader"), 1)
        self.assertEqual(types.count("CLIPTextEncode"), 2)
        self.assertEqual(types.count("SkipLayerGuidanceDiTSimple"), 1)
        self.assertEqual(types.count("KSampler"), 1)
        self.assertEqual(types.count("SaveImage"), 1)
        clip = next(n["inputs"] for n in api.values() if n["class_type"] == "CLIPLoader")
        self.assertEqual(clip["type"], "moss_image")
        self.assertEqual(clip["clip_name"], "qwen3.5_9b_w4a8_gptq.safetensors")
        unet = next(n["inputs"] for n in api.values() if n["class_type"] == "UNETLoader")
        self.assertEqual(unet["unet_name"], "moss_image_sft_int8_convrot.safetensors")
        ks = next(n["inputs"] for n in api.values() if n["class_type"] == "KSampler")
        self.assertEqual((ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]), (25, 2.5, "er_sde", "simple"))
        slg = next(n["inputs"] for n in api.values() if n["class_type"] == "SkipLayerGuidanceDiTSimple")
        self.assertEqual(slg["single_layers"], "22")
        # SLG 串在 MODEL 链上：KSampler.model 来自 SLG 输出
        refs = _link_targets(api)
        ks_nid = next(nid for nid, n in api.items() if n["class_type"] == "KSampler")
        slg_nid = next(nid for nid, n in api.items() if n["class_type"] == "SkipLayerGuidanceDiTSimple")
        self.assertEqual(refs[ks_nid]["model"], slg_nid)
        self.assertEqual(refs[slg_nid]["model"],
                         next(nid for nid, n in api.items() if n["class_type"] == "UNETLoader"))
        # 负向编码节点保留官方负向提示词
        texts = sorted(n["inputs"]["text"] for n in api.values() if n["class_type"] == "CLIPTextEncode")
        self.assertTrue(any("nsfw" in t for t in texts))

    def test_klein_structure_matches_official_template(self):
        api = KLEIN_WF["api"]
        types = [n["class_type"] for n in api.values()]
        self.assertEqual(types.count("SkipLayerGuidanceDiTSimple"), 0)  # 蒸馏线无 SLG
        clip = next(n["inputs"] for n in api.values() if n["class_type"] == "CLIPLoader")
        self.assertEqual(clip["type"], "flux3")
        self.assertEqual(clip["clip_name"], "qwen3vl_4b_int8_convrot.safetensors")
        unet = next(n["inputs"] for n in api.values() if n["class_type"] == "UNETLoader")
        self.assertEqual(unet["unet_name"], "flux3-image-klein-int8-convrot.safetensors")
        ks = next(n["inputs"] for n in api.values() if n["class_type"] == "KSampler")
        self.assertEqual((ks["steps"], ks["cfg"], ks["sampler_name"]), (16, 1.0, "euler"))
        vae = next(n["inputs"] for n in api.values() if n["class_type"] == "VAELoader")
        self.assertEqual(vae["vae_name"], "flux2-vae.safetensors")

    def test_create_page_size_injection_compat(self):
        # 创作页 hasLatentSize 正则 /Latent/i 依赖 Latent 类节点存在
        for wf in (MOSS_WF, KLEIN_WF):
            self.assertTrue(any("Latent" in n["class_type"] for n in wf["api"].values()))

    def test_loader_files_covered_by_preset_suites(self):
        preset_files = {(m["dir"], m["name"]) for s in server.PRESET_SUITES for m in s["models"]}
        for wf in (MOSS_WF, KLEIN_WF):
            for n in wf["api"].values():
                if n["class_type"] == "UNETLoader":
                    self.assertIn(("diffusion_models", n["inputs"]["unet_name"]), preset_files)
                elif n["class_type"] == "CLIPLoader":
                    self.assertIn(("text_encoders", n["inputs"]["clip_name"]), preset_files)
                elif n["class_type"] == "VAELoader":
                    self.assertIn(("vae", n["inputs"]["vae_name"]), preset_files)


class TestPresetSuites(unittest.TestCase):
    def test_new_suites_present(self):
        ids = [s["id"] for s in server.PRESET_SUITES]
        self.assertIn("mossimage", ids)
        self.assertIn("flux3klein", ids)

    def test_model_entries_wellformed(self):
        for s in server.PRESET_SUITES:
            for m in s["models"]:
                self.assertIn(m["dir"], server.MODEL_SUBDIRS, f"{m['name']} 目录非法")
                if s["id"] in ("mossimage", "flux3klein"):
                    # 新套件清单必须带精确体积（模型页进度条与一键下载依赖）
                    self.assertGreater(m["size"], 0, f"{m['name']} size 应为正数")
                if m.get("url") is not None:
                    self.assertTrue(m["url"].startswith("https://hf-mirror.com/"),
                                    f"{m['name']} 下载地址必须走 hf-mirror")

    def test_moss_suite_ungated_downloads(self):
        s = next(x for x in server.PRESET_SUITES if x["id"] == "mossimage")
        for m in s["models"]:
            self.assertIsNotNone(m["url"], f"MOSS 套件 {m['name']} 应可一键下载")
            self.assertIn("Comfy-Org/MOSS-Image", m["url"])

    def test_klein_gated_files_honest(self):
        s = next(x for x in server.PRESET_SUITES if x["id"] == "flux3klein")
        by_name = {m["name"]: m for m in s["models"]}
        # BFL gated：主模型与编码器不提供匿名直链
        self.assertIsNone(by_name["flux3-image-klein-int8-convrot.safetensors"]["url"])
        self.assertIsNone(by_name["qwen3vl_4b_int8_convrot.safetensors"]["url"])
        # VAE 与 MOSS 仓库逐字节相同（LFS sha256 一致），走一键下载
        self.assertIn("Comfy-Org/MOSS-Image", by_name["flux2-vae.safetensors"]["url"])


class TestTextOverrideScoping(unittest.TestCase):
    def _submit(self, wf, overrides):
        comfy = Mock()
        comfy.http.return_value = {"prompt_id": "pid-test"}
        with patch.object(server, "COMFY", comfy), \
             patch.object(server, "add_run", Mock()), \
             patch.object(server, "SETTINGS", {"client_id": "t"}):
            r = server.submit_workflow(wf, times=1, overrides=dict(overrides))
        self.assertTrue(r["ok"], r.get("msg"))
        return comfy.http.call_args.kwargs["payload"]["prompt"]

    def test_text_only_hits_first_clip_text_encode(self):
        # MOSS：正向被覆盖，官方负向提示词必须原样保留
        prompt = self._submit(MOSS_WF, {"text": "雪夜竹林剑客"})
        encodes = [n["inputs"]["text"] for n in prompt.values() if n["class_type"] == "CLIPTextEncode"]
        self.assertIn("雪夜竹林剑客", encodes)
        self.assertTrue(any("nsfw" in t for t in encodes))

    def test_width_height_reach_flux2_latent(self):
        prompt = self._submit(MOSS_WF, {"text": "x", "width": 1024, "height": 1536})
        latent = next(n["inputs"] for n in prompt.values() if n["class_type"] == "EmptyFlux2LatentImage")
        self.assertEqual((latent["width"], latent["height"]), (1024, 1536))

    def test_h3_style_prompt_key_single_node_unchanged(self):
        wf = {"id": "fake-h3", "name": "fake", "api": {
            "1": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "old", "seed": 0}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "h3"}},
        }}
        prompt = self._submit(wf, {"text": "new"})
        self.assertEqual(prompt["1"]["inputs"]["prompt"], "new")


if __name__ == "__main__":
    unittest.main()
