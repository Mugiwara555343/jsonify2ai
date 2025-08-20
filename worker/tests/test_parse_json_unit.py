import json
from app.services.parse_json import extract_text_from_json, extract_text_from_jsonl

def test_extract_text_from_json(tmp_path):
    p = tmp_path / "s.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"user": {"name": "bob", "age": 25}, "tags": ["x", "y"]}, f)
    txt = extract_text_from_json(str(p))
    assert "user.name: bob" in txt
    assert "user.age: 25" in txt
    assert "tags[0]: x" in txt

def test_extract_text_from_jsonl(tmp_path):
    p = tmp_path / "s.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"a": 1}) + "\n")
        f.write(json.dumps({"b": 2}) + "\n")
    txt = extract_text_from_jsonl(str(p))
    assert "$[0].a: 1" in txt and "$[1].b: 2" in txt
