"""convert_ui_to_api 的子图（definitions.subgraphs）展开测试。

官方 SCAIL-2 模板风格：子图输入槽同时穿透到内部节点的 widget（值存在 widget 上）
和数据输入（如 ComfyMathExpression 的多输入）；外层引用节点 widgets_values 为空。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402


def _sub_ui():
    """主图: LoadImage(1) -> 子图(2) -> SaveImage(3)；子图内部: CLIPTextEncode(11)"""
    sub_id = "aaaaaaaa-1111-2222-3333-444444444444"
    ui = {
        "nodes": [
            {"id": 1, "type": "LoadImage", "inputs": [], "widgets_values": ["a.png", "image"]},
            {"id": 2, "type": sub_id,
             "inputs": [
                 {"name": "images", "link": 10},
                 {"name": "text", "widget": {"name": "text"}, "link": None},
             ],
             "outputs": [{"name": "IMAGE"}], "widgets_values": []},
            {"id": 3, "type": "SaveImage", "inputs": [{"name": "images", "link": 12}], "widgets_values": ["out"]},
        ],
        "links": [
            [10, 1, 0, 2, 0, "IMAGE"],
            [12, 2, 0, 3, 0, "IMAGE"],
        ],
        "definitions": {"subgraphs": [{
            "id": sub_id,
            "inputs": [
                {"id": "i0", "name": "images", "type": "IMAGE", "linkIds": [101]},
                {"id": "i1", "name": "text", "type": "STRING", "linkIds": [102]},
            ],
            "outputs": [{"id": "o0", "name": "IMAGE", "linkIds": [103]}],
            "nodes": [
                # widget 值留在内部节点上；inputs 数组的 widget 槽带 widget 标记
                {"id": 11, "type": "CLIPTextEncode",
                 "inputs": [{"name": "clip", "link": None}, {"name": "text", "widget": {"name": "text"}, "link": 102}],
                 "widgets_values": ["a cat"]},
                # 真数据端点：images 穿透进 ImageInvert 的连线输入
                {"id": 12, "type": "ImageInvert",
                 "inputs": [{"name": "images", "link": 101}],
                 "widgets_values": []},
            ],
            "links": [
                {"id": 101, "origin_id": -10, "origin_slot": 0, "target_id": 12, "target_slot": 0, "type": "IMAGE"},
                # text 槽穿透到 CLIPTextEncode 的 widget（widget 绑定线）
                {"id": 102, "origin_id": -10, "origin_slot": 1, "target_id": 11, "target_slot": 1, "type": "STRING"},
                {"id": 103, "origin_id": 12, "origin_slot": 0, "target_id": -20, "target_slot": 0, "type": "IMAGE"},
            ],
        }]},
        "version": 0.6,
    }
    return ui, sub_id


def test_flatten_structure():
    ui, _ = _sub_ui()
    flat = server._flatten_subgraphs(ui)
    ids = {str(n["id"]) for n in flat["nodes"]}
    assert "2x11" in ids and "2x12" in ids, ids
    assert "2" not in ids, "UUID 引用节点应被移除"
    # 全部连线端点均存在
    for l in flat["links"]:
        assert str(l[1]) in ids and str(l[3]) in ids, l
    # 每个被引用的 link 都存在
    lk = {l[0] for l in flat["links"]}
    for n in flat["nodes"]:
        for i in n.get("inputs") or []:
            assert i.get("link") is None or i["link"] in lk, (n["id"], i)


def test_flatten_data_flow():
    ui, _ = _sub_ui()
    flat = server._flatten_subgraphs(ui)
    # LoadImage -> 子图内部 ImageInvert
    bridge = [l for l in flat["links"] if str(l[1]) == "1" and str(l[3]) == "2x12"]
    assert bridge, "主图输入应桥接到子图内部数据端点"
    # 子图输出 ImageInvert -> SaveImage
    bridge = [l for l in flat["links"] if str(l[1]) == "2x12" and l[3] == 3]
    assert bridge, "子图输出应桥接到主图消费者"


def test_convert_with_schema():
    ui, _ = _sub_ui()
    object_info = {
        "LoadImage": {"input": {"required": {"image": [["a.png"]], "image_upload": [["x"]]}}},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["out"]}}},
        "CLIPTextEncode": {"input": {"required": {"clip": ["CLIP"], "text": ["STRING"]}}},
        "ImageInvert": {"input": {"required": {"images": ["IMAGE"]}}},
    }
    api, warns = server.convert_ui_to_api(ui, object_info)
    enc = next(v for v in api.values() if v["class_type"] == "CLIPTextEncode")
    # widget 绑定线被清掉后，text 应从内部节点 widgets_values 消费
    assert enc["inputs"].get("text") == "a cat", enc["inputs"]
    # 主图桥接：LoadImage 的图进 ImageInvert，ImageInvert 出图进 SaveImage
    assert any(isinstance(v, list) and str(v[0]) == "2x12" for v in api["3"]["inputs"].values()), api["3"]


def test_primitive_slot_default():
    """无主图连线且值在 widget 端点的 INT 槽穿透到数据输入时，应由 PrimitiveInt 承载。"""
    sub_id = "bbbbbbbb-1111-2222-3333-444444444444"
    ui = {
        "nodes": [
            {"id": 2, "type": sub_id,
             "inputs": [{"name": "count", "widget": {"name": "count"}, "link": None}],
             "outputs": [], "widgets_values": []},
        ],
        "links": [],
        "definitions": {"subgraphs": [{
            "id": sub_id,
            "inputs": [{"id": "i0", "name": "count", "type": "INT", "linkIds": [201, 202]}],
            "outputs": [],
            "nodes": [
                # widget 绑定端点：EmptyLatentImage.batch_size 承载值 3
                {"id": 21, "type": "EmptyLatentImage",
                 "inputs": [{"name": "batch_size", "widget": {"name": "batch_size"}, "link": 201}],
                 "widgets_values": [512, 512, 3]},
                # 数据端点：Math 节点的多输入
                {"id": 22, "type": "MathExpression",
                 "inputs": [{"name": "a", "link": None}, {"name": "b", "link": 202}],
                 "widgets_values": ["a * b"]},
            ],
            "links": [
                {"id": 201, "origin_id": -10, "origin_slot": 0, "target_id": 21, "target_slot": 2, "type": "INT"},
                {"id": 202, "origin_id": -10, "origin_slot": 0, "target_id": 22, "target_slot": 1, "type": "INT"},
            ],
        }]},
        "version": 0.6,
    }
    flat = server._flatten_subgraphs(ui)
    types = {n["type"] for n in flat["nodes"]}
    assert "PrimitiveInt" in types, types
    prim = next(n for n in flat["nodes"] if n["type"] == "PrimitiveInt")
    assert prim["widgets_values"] == [3], prim
    math = next(n for n in flat["nodes"] if n["type"] == "MathExpression")
    b_link = math["inputs"][1]["link"]
    links = {l[0]: l for l in flat["links"]}
    assert b_link in links and links[b_link][1] == prim["id"], (math, links.get(b_link))


def test_nested_subgraph_rejected():
    ui, sub_id = _sub_ui()
    ui["definitions"]["subgraphs"][0]["nodes"].append(
        {"id": 99, "type": sub_id, "inputs": [], "outputs": [], "widgets_values": []})
    try:
        server._flatten_subgraphs(ui)
        assert False, "嵌套子图应抛错"
    except ValueError:
        pass


if __name__ == "__main__":
    test_flatten_structure()
    test_flatten_data_flow()
    test_convert_with_schema()
    test_primitive_slot_default()
    test_nested_subgraph_rejected()
    print("OK")
