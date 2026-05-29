from mockwork.json_utils import extract_json_object


def test_extract_json_object_from_plain_json():
    assert extract_json_object('{"ok": true}') == {"ok": True}


def test_extract_json_object_from_markdown_fence():
    assert extract_json_object('```json\n{"items": [1, 2]}\n```') == {"items": [1, 2]}


def test_extract_json_object_from_surrounding_text():
    assert extract_json_object('结果如下：{"value": 3}') == {"value": 3}


def test_extract_json_object_from_python_literal():
    assert extract_json_object("{'items': [{'ok': True, 'value': None}]}") == {
        "items": [{"ok": True, "value": None}]
    }
