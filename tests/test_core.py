# -*- coding: utf-8 -*-
"""核心流程单元测试：分镜解析 / UI→API 转换 / 参数覆盖。运行：python -m unittest tests.test_core"""
import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import parse_script_text, convert_ui_to_api, LLM_PRESETS, STYLE_SOPS


class TestScriptParser(unittest.TestCase):
    def test_shot_blocks(self):
        text = '''## 二、H3 提示词

### S01E01_SHOT01 【V3·2D】
```text
integrated_multimodal_description: cinematic close-up, test subject A.
overall_soundscape: rain.
```

### S01E01_SHOT02 【V2·3D】
```text
integrated_multimodal_description: wide shot, test subject B.
```
'''
        items = parse_script_text(text)
        self.assertEqual(len(items), 2)
        self.assertIn('SHOT01', items[0]['name'])
        self.assertIn('close-up', items[0]['prompt'])

    def test_pipe_rows_fallback(self):
        text = '| SHOT01 | 中景 | 深夜办公室 |\n| SHOT02 | 特写 | 破木梁屋顶 |'
        items = parse_script_text(text)
        self.assertEqual(len(items), 2)
        self.assertIn('SHOT01', items[0]['name'])

    def test_empty(self):
        self.assertEqual(parse_script_text(''), [])


class TestStyles(unittest.TestCase):
    def test_all_have_fields(self):
        for sid, s in STYLE_SOPS.items():
            self.assertIn('name', s)
            self.assertIn('direction', s)
            self.assertIn('tokens', s)

    def test_llm_presets(self):
        for pid, p in LLM_PRESETS.items():
            self.assertIn('name', p)
            self.assertIn('base', p)


if __name__ == '__main__':
    unittest.main()
