# -*- coding: utf-8 -*-
"""参考生视频 + 台词/反应镜头 lint + SRT/剪辑单 回归测试。
运行：python -m unittest tests.test_ref2v_shortdrama"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

REF2V = next(w for w in server.list_workflows() if w.get("id") == "h3-ref2v")


class TestRefSlots(unittest.TestCase):
    def test_slots_found(self):
        sl = server.ref_slots(REF2V["api"])
        self.assertEqual(len(sl["image"]), 9)
        self.assertEqual(len(sl["audio"]), 3)
        self.assertTrue(server.wf_supports(REF2V, "ref_image_1"))

    def test_prune_keeps_used_only(self):
        pr = server.prune_ref_graph(REF2V["api"], 2, 1)
        ins = pr["6"]["inputs"]
        self.assertIn("ref_image_1", ins)
        self.assertIn("ref_image_2", ins)
        self.assertNotIn("ref_image_3", ins)
        self.assertIn("ref_audio_1", ins)
        self.assertNotIn("ref_audio_2", ins)
        # 被剪掉的占位节点要从图里移除
        self.assertNotIn("33", pr)
        self.assertNotIn("42", pr)
        # 原图不能被改
        self.assertIn("ref_image_3", REF2V["api"]["6"]["inputs"])

    def test_prune_zero_refs(self):
        pr = server.prune_ref_graph(REF2V["api"], 0, 0)
        self.assertFalse([k for k in pr["6"]["inputs"] if re.fullmatch(r"ref_image_\d+", k)])

    def test_tag_prompt(self):
        p = server.ref_tag_prompt("羊羊站在庭院。", ["羊羊的长相", "书院庭院"], ["羊羊的声音"])
        self.assertIn("<Picture 1> is 羊羊的长相", p)
        self.assertIn("<Picture 2> is 书院庭院", p)
        self.assertIn("<Audio 1> is 羊羊的声音", p)
        self.assertTrue(p.startswith("羊羊站在庭院。"))
        self.assertEqual(server.ref_tag_prompt("x", [], []), "x")

    def test_routing_prefers_ref2v(self):
        wf, up = server.resolve_shot_workflow({"refs": [{"path": "a.png"}]},
                                              next(w for w in server.list_workflows() if w.get("id") == "h3-i2v"))
        self.assertTrue(up)
        self.assertEqual(wf["id"], "h3-ref2v")


class TestDialogueLint(unittest.TestCase):
    def test_dialogue_stats(self):
        ds = server.dialogue_stats('羊羊说：「其实，我是诗仙。」老师内心独白：「此人必输。」')
        self.assertEqual(ds["chars"], 13)
        self.assertTrue(ds["has_monologue"])
        self.assertTrue(ds["has_speech"])

    def test_too_long_dialogue_warns(self):
        # 5 秒 ≈ 25 字预算；这里 40 字
        long_line = "这" * 40
        pre = server.precheck_shot({"prompt": f'羊羊说：「{long_line}」', "gen_secs": 5})
        self.assertIn("DIALOGUE_TOO_LONG", [w["code"] for w in pre["warns"]])

    def test_untagged_dialogue_warns(self):
        pre = server.precheck_shot({"prompt": '「其实，我是诗仙。」', "gen_secs": 5})
        codes = [w["code"] for w in pre["warns"]]
        self.assertIn("DIALOGUE_UNTAGGED", codes)

    def test_reaction_with_lines_warns(self):
        pre = server.precheck_shot({"prompt": '「什么？」', "kind": "reaction", "gen_secs": 3})
        self.assertIn("REACTION_HAS_LINES", [w["code"] for w in pre["warns"]])

    def test_refs_not_referenced_warns(self):
        pre = server.precheck_shot({"prompt": "羊羊站在庭院。", "refs": [{"path": "a.png", "label": "羊羊"}]},
                                   REF2V)
        self.assertIn("REFS_NOT_REFERENCED", [w["code"] for w in pre["warns"]])

    def test_refs_referenced_ok(self):
        pre = server.precheck_shot({"prompt": "羊羊站在庭院。<Picture 1> 是羊羊。"},
                                   REF2V, palette=None)
        self.assertNotIn("REFS_NOT_REFERENCED", [w["code"] for w in pre["warns"]])


class TestExports(unittest.TestCase):
    def test_srt(self):
        items = [{"prompt": '羊羊说：「其实，我是诗仙。」', "gen_secs": 4},
                 {"prompt": "众人哄笑", "gen_secs": 2},
                 {"prompt": '李秀才说：「无知者无畏。」', "gen_secs": 3}]
        srt = server.shots_to_srt(items)
        self.assertIn("00:00:00,000 --> 00:00:04,000", srt)
        self.assertIn("其实，我是诗仙。", srt)
        self.assertIn("00:00:06,000 --> 00:00:09,000", srt)
        self.assertNotIn("众人哄笑", srt)  # 无台词不出字幕

    def test_edit_sheet(self):
        b = {"name": "E01", "items": [{"name": "S1", "prompt": '「甲。」', "gen_secs": 4},
                                      {"name": "S2", "kind": "reaction", "gen_secs": 2, "seed": 7}]}
        md = server.edit_sheet_md(b)
        self.assertIn("| 1 | S1 | dialogue | 4 |", md)
        self.assertIn("反应镜头（无台词）", md)
        self.assertIn("seed=7", md)
        self.assertIn("总时长：6.0 秒", md)


if __name__ == "__main__":
    unittest.main()
