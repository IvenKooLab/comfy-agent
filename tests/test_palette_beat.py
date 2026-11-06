# -*- coding: utf-8 -*-
"""配色前置 + 节拍对齐回归测试。运行：python -m unittest tests.test_palette_beat"""
import array
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def _click_pcm(bpm=120.0, seconds=8.0, rate=8000):
    """合成脉冲串（每拍一个短促强音），用于验证 BPM 估计。"""
    n = int(rate * seconds)
    samples = array.array("h", [0]) * n
    period = 60.0 / bpm
    t = 0.0
    while t < seconds:
        i = int(t * rate)
        for k in range(int(rate * 0.04)):  # 40ms 衰减脉冲
            if i + k < n:
                samples[i + k] = int(12000 * (1 - k / (rate * 0.04)))
        t += period
    return samples.tobytes()


class TestPalette(unittest.TestCase):
    def test_hex_and_luma(self):
        self.assertEqual(server.hex_to_rgb("#ff0000"), (255, 0, 0))
        self.assertEqual(server.hex_to_rgb("bad"), (43, 43, 48))
        self.assertAlmostEqual(server.luma_255((255, 255, 255)), 255, places=0)
        self.assertAlmostEqual(server.luma_255((0, 0, 0)), 0, places=0)

    def test_value_separation(self):
        hi = server.value_separation({"bg": "#101010", "subject": "#f0f0f0"})
        lo = server.value_separation({"bg": "#4a4a4a", "subject": "#525252"})
        self.assertGreater(hi, 150)
        self.assertLess(lo, 25)

    def test_low_contrast_warns_in_precheck(self):
        pre = server.precheck_shot({"prompt": "x" * 40}, {"id": "w", "api": {}},
                                   palette={"bg": "#4a4a4a", "subject": "#525252"})
        self.assertIn("PALETTE_LOW_CONTRAST", [w["code"] for w in pre["warns"]])

    def test_sheet_html(self):
        b = {"name": "E01", "palette": {"bg": "#101820", "subject": "#f2e8dc"},
             "items": [{"name": "S1", "gen_secs": 5}, {"name": "S2"}]}
        html = server.palette_sheet_html(b)
        self.assertIn("38%", html)
        self.assertIn("62%", html)
        self.assertIn("色板总表", html)
        self.assertEqual(html.count("<svg"), 4)  # 每镜彩色 + 黑白各一张
        self.assertIn("亮度差", html)


class TestBeat(unittest.TestCase):
    def test_bpm_estimation(self):
        with patch.object(server, "_decode_pcm", return_value=_click_pcm(120.0, 8.0)):
            a = server.beat_analysis("fake.mp3")
        self.assertTrue(a["ok"], a)
        self.assertAlmostEqual(a["bpm"], 120.0, delta=6.0)
        self.assertGreater(len(a["beats"]), 8)

    def test_bpm_hint_corrects_octave(self):
        with patch.object(server, "_decode_pcm", return_value=_click_pcm(120.0, 8.0)):
            a = server.beat_analysis("fake.mp3", bpm_hint=120)
        self.assertAlmostEqual(a["bpm"], 120.0, delta=1.0)

    def test_align_snaps_to_bar(self):
        with patch.object(server, "_decode_pcm", return_value=_click_pcm(120.0, 30.0)):
            b = {"name": "E01", "items": [{"name": "S1", "gen_secs": 5}, {"name": "S2", "gen_secs": 5}]}
            r = server.beat_align(b, "fake.mp3")
        self.assertTrue(r["ok"], r)
        # 120BPM → 每拍 0.5s，每小节 2s；5s 应吸附到 6s 或 4s（取整小节）
        self.assertAlmostEqual(r["bar_secs"], 2.0, delta=0.3)
        for s in r["shots"]:
            self.assertAlmostEqual(s["suggest"] % r["bar_secs"] < r["bar_secs"], True)
            self.assertAlmostEqual(round(s["suggest"] / r["bar_secs"]), s["suggest"] / r["bar_secs"], places=2)
        self.assertIn("beat", b)
        self.assertEqual(b["beat"]["bpm"], r["bpm"])

    def test_bad_audio_returns_error(self):
        with patch.object(server, "_decode_pcm", return_value=None):
            r = server.beat_analysis("nope.mp3")
        self.assertFalse(r["ok"])
        self.assertIn("解码失败", r["error"])


if __name__ == "__main__":
    unittest.main()
