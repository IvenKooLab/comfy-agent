# -*- coding: utf-8 -*-
"""助手链路升级回归测试：确定性实体解析 / LLM 动作校验 / @显式路由 /
动作序列断点续跑 / 生成反馈统计。运行：python -m unittest tests.test_agent_upgrades"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class TestEntityResolution(unittest.TestCase):
    def test_levenshtein_cap(self):
        self.assertEqual(server._levenshtein("abc", "abc", cap=2), 0)
        self.assertEqual(server._levenshtein("abc", "abd", cap=2), 1)
        # 长度差超 cap 直接早退
        self.assertEqual(server._levenshtein("abcdef", "a", cap=2), 3)

    def test_exact_normalized(self):
        for frag in ("Flux 文生图", "Flux文生图", "flux文生图（内置）"):
            r = server.resolve_entity("workflow", frag)
            self.assertIsNotNone(r, frag)
            self.assertEqual(r[0], "builtin-flux")

    def test_typo_corrected(self):
        r = server.resolve_entity("workflow", "F1ux 文生图")
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "builtin-flux")
        r2 = server.resolve_entity("style", "国漫使劲")
        self.assertIsNotNone(r2)
        self.assertEqual(r2[0], "guoman_epic")

    def test_miss_returns_none_no_new_entity(self):
        self.assertIsNone(server.resolve_entity("workflow", "完全不存在的模型"))
        self.assertIsNone(server.resolve_entity("workflow", ""))

    def test_find_wf_by_id(self):
        wf = server.find_wf_smart("builtin-moss")
        self.assertIsNotNone(wf)
        self.assertEqual(wf["id"], "builtin-moss")


class TestLLMActionValidation(unittest.TestCase):
    def test_rejects_unknown_keys(self):
        with self.assertRaises(ValueError):
            server.validate_llm_actions({"hack": {}})

    def test_rejects_non_object_and_bad_actions(self):
        with self.assertRaises(ValueError):
            server.validate_llm_actions([1, 2])
        with self.assertRaises(ValueError):
            server.validate_llm_actions({"actions": []})
        with self.assertRaises(ValueError):
            server.validate_llm_actions({"actions": [{"run": {}}] * 11})

    def test_workflow_converges_to_local_id(self):
        out = server.validate_llm_actions({"run": {"workflow": "Flux 文生图", "times": 3, "seed": "42"}})
        a = out["actions"][0]["run"]
        self.assertEqual(a["workflow"], "builtin-flux")
        self.assertEqual((a["times"], a["seed"]), (3, 42))

    def test_unresolvable_workflow_becomes_hint(self):
        out = server.validate_llm_actions({"run": {"workflow": "不存在", "times": 1}})
        self.assertIn("reply", out)
        self.assertIn("没找到工作流", out["reply"])

    def test_domains_clamped(self):
        out = server.validate_llm_actions({"archive": {"count": 999}})
        self.assertEqual(out["actions"][0]["archive"]["count"], 30)
        out = server.validate_llm_actions({"open": {"view": "nope"}})
        self.assertEqual(out["actions"][0]["open"]["view"], "gallery")
        out = server.validate_llm_actions({"run": {"workflow": "builtin-flux", "times": 999}})
        self.assertEqual(out["actions"][0]["run"]["times"], 20)

    def test_multi_action_nested(self):
        out = server.validate_llm_actions({"actions": [
            {"status": {}}, {"run": {"workflow": "builtin-flux", "times": 1}}]})
        self.assertEqual(len(out["actions"]), 2)


class TestExplicitEntityRouting(unittest.TestCase):
    def test_norm_entities_drop_invalid(self):
        ents = server._norm_entities([
            {"kind": "workflow", "id": "builtin-moss", "name": "x"},
            {"kind": "workflow", "id": "NOT-EXIST", "name": "y"},
            {"kind": "style", "id": "guoman_epic", "name": "国漫史诗"},
            {"kind": "character", "id": "fake", "name": "z"},
        ])
        self.assertIn("workflow", ents)
        self.assertEqual(ents["workflow"]["id"], "builtin-moss")
        self.assertIn("style", ents)
        self.assertNotIn("character", ents)

    def test_char_lora_injection(self):
        g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "a"}},
             "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}}}
        out = server._inject_char_lora(g, {"lora": "char_a.safetensors", "lora_strength": 0.7})
        self.assertIn("char_lora", out)
        self.assertEqual(out["char_lora"]["inputs"]["lora_name"], "char_a.safetensors")
        self.assertEqual(out["2"]["inputs"]["model"][0], "char_lora")
        # 原图不被污染
        self.assertEqual(g["2"]["inputs"]["model"][0], "1")

    def test_char_lora_existing_node_overwrite(self):
        g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "a"}},
             "3": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "old", "strength_model": 1, "model": ["1", 0]}}}
        out = server._inject_char_lora(g, {"lora": "new", "lora_strength": 0.5})
        self.assertNotIn("char_lora", out)
        self.assertEqual(out["3"]["inputs"]["lora_name"], "new")

    def test_draw_honors_bound_character_and_workflow(self):
        g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "a"}},
             "2": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}}
        fake_char = {"id": "c1", "name": "剑客", "lock": "白衣剑客", "lora": "char.safetensors"}
        with patch.object(server, "list_characters", return_value=[fake_char]), \
             patch.object(server, "enhance_prompt_tracked",
                          return_value={"ok": True, "english": "EN"}) as enh, \
             patch.object(server, "submit_workflow",
                          return_value={"ok": True, "msg": "提交成功", "prompt_ids": ["p1"]}) as sub:
            out = server.agent_execute("画：雪夜竹林", entities=[
                {"kind": "workflow", "id": "builtin-moss", "name": "MOSS"},
                {"kind": "character", "id": "c1", "name": "剑客"},
            ])
        self.assertTrue(out["reply"])
        self.assertEqual(sub.call_args[0][0]["name"], "MOSS-Image 文生图（内置）")  # 显式 ID 直路由
        # 角色锁定串注入了增强前的提示词
        self.assertIn("白衣剑客", enh.call_args[0][0])
        # 角色 LoRA 已注入执行图
        self.assertIn("char_lora", sub.call_args[0][0]["api"])

    def test_bound_workflow_overrides_llm_output(self):
        """@显式绑定压过 LLM 输出里的其它工作流名（跳过猜测的核心承诺）。"""
        llm_json = json.dumps({"run": {"workflow": "Flux 文生图（内置）", "times": 1}})
        with patch.object(server, "SETTINGS", {"llm_key": "k"}), \
             patch.object(server, "agent_intent_llm", return_value=llm_json), \
             patch.object(server, "run_action_plan", wraps=server.run_action_plan) as plan, \
             patch.object(server, "submit_workflow",
                          return_value={"ok": True, "msg": "ok", "prompt_ids": ["p1"]}):
            server.agent_execute("再来几张", entities=[{"kind": "workflow", "id": "builtin-moss", "name": "MOSS"}])
        acts = plan.call_args[0][0]
        self.assertEqual(acts[0]["run"]["workflow"], "builtin-moss")


class TestActionPlans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_file = patch.object(server, "PLAN_FILE", os.path.join(self.tmp.name, "plans.json"))
        self.patch_file.start()

    def tearDown(self):
        self.patch_file.stop()
        self.tmp.cleanup()

    def test_failed_midway_then_resume(self):
        calls = []

        def fake_coerce(a):
            calls.append(a)
            idx = len(calls)
            # 第 2 步（第一次执行）失败；续跑时全部成功
            if idx == 2:
                return {"reply": "ComfyUI 离线", "actions": [], "ok": False}
            return {"reply": f"step{idx} ok", "actions": [], "ok": True}

        actions = [{"status": {}}, {"status": {}}, {"status": {}}]
        with patch.object(server, "agent_execute_coerce", side_effect=fake_coerce):
            r1 = server.run_action_plan(actions, "测试多步", [])
            self.assertEqual(len(calls), 2)
            plan_action = next(a for a in r1["actions"] if a["type"] == "plan")
            self.assertEqual(plan_action["status"], "failed")
            self.assertEqual(plan_action["done"], 1)
            plans = server.load_plans()
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0]["status"], "failed")  # 状态确实落盘
            self.assertEqual(plans[0]["done"], 1)  # 失败步不算完成，指针停在它前面

            r2 = server.resume_plan(plan_action["plan_id"])
            # 断点从第 2 步起重跑（失败步 + 第 3 步）
            self.assertEqual(len(calls), 4)
            self.assertTrue(any(a.get("type") == "plan" and a.get("status") == "done" for a in r2["actions"]))
            self.assertEqual(server.load_plans()[0]["status"], "done")

    def test_single_action_no_plan(self):
        with patch.object(server, "PLAN_FILE", os.path.join(self.tmp.name, "plans_single.json")), \
             patch.object(server, "agent_execute_coerce", return_value={"reply": "done", "actions": [], "ok": True}):
            r = server.run_action_plan([{"status": {}}], "单步", [])
        self.assertFalse(any(a.get("type") == "plan" for a in r["actions"]))

    def test_resume_unknown_plan(self):
        r = server.resume_plan("no-such-plan")
        self.assertIn("不存在", r["reply"])


class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_file = patch.object(server, "FEEDBACK_FILE", os.path.join(self.tmp.name, "feedback.jsonl"))
        self.patch_file.start()

    def tearDown(self):
        self.patch_file.stop()
        self.tmp.cleanup()

    def test_stats_empty(self):
        s = server.feedback_stats()
        self.assertEqual(s["total_events"], 0)
        self.assertIsNone(s["adoption_rate"])

    def test_adoption_rates_and_rates(self):
        # 绕过文件参数解析，直接写事件
        with patch.object(server, "_feedback_params", return_value={"model": "flux1-dev-fp8.safetensors", "prompt": "x"}):
            server.record_feedback("adopt_archive", "a.png")
            server.record_feedback("adopt_archive", "b.png")
            server.record_feedback("delete", "c.png")
            server.record_feedback("rerun", "d.png")
        server.record_feedback("enhance_ok", "", extra={"engine": "llm"})
        server.record_feedback("enhance_fail", "", extra={})
        s = server.feedback_stats()
        self.assertEqual((s["adopted"], s["deleted"]), (2, 1))
        self.assertAlmostEqual(s["adoption_rate"], 2 / 3, places=3)
        self.assertEqual(s["by_model"]["flux1-dev-fp8.safetensors"], {"adopted": 2, "deleted": 1})
        self.assertEqual(s["enhance"]["fail_rate"], 0.5)
        self.assertEqual(s["rerun"]["count"], 1)

    def test_enhance_tracked_records(self):
        with patch.object(server, "enhance_prompt", return_value={"ok": True, "english": "x", "engine": "llm"}):
            server.enhance_prompt_tracked("测试")
        s = server.feedback_stats()
        self.assertEqual(s["enhance"]["ok"], 1)
        self.assertEqual(s["enhance"]["fail"], 0)


if __name__ == "__main__":
    unittest.main()
