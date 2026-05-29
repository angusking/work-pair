from mockwork.initializer import extract_json_from_markdown, normalize_asset_list


def test_extract_json_from_markdown_returns_all_json_blocks():
    content = """
# Members

```json
{"member_id": "M001", "name": "A"}
```

```json
{"member_id": "M002", "name": "B"}
```
"""

    assert extract_json_from_markdown(content) == [
        {"member_id": "M001", "name": "A"},
        {"member_id": "M002", "name": "B"},
    ]


def test_normalize_asset_list_unwraps_wrapper_key():
    assert normalize_asset_list({"members": [{"member_id": "M001"}]}, "members") == [
        {"member_id": "M001"}
    ]


def test_normalize_asset_list_wraps_single_object():
    assert normalize_asset_list({"task_id": "T001"}, "tasks") == [{"task_id": "T001"}]
