import json
from pathlib import Path
from note_to_json.parser import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "sample.md"


def test_parse_returns_valid_json():
    data = parse_file(FIXTURE)
    assert isinstance(data, dict)
    assert "title" in data and isinstance(data["title"], str)
    json.dumps(data)  # ensures serialisable


def test_parse_extracts_required_fields():
    data = parse_file(FIXTURE)
    required_fields = ["title", "timestamp", "raw_text", "plain_text"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"


def test_parse_extracts_metadata():
    data = parse_file(FIXTURE)
    assert data["title"] == "Test Entry"
    assert data["date"] == "2025-01-15"
    assert data["tone"] == "Neutral"
    assert "test" in data["tags"]
    assert "demo" in data["tags"]
    assert "pytest" in data["tags"]


def test_parse_extracts_summary_and_reflections():
    data = parse_file(FIXTURE)
    assert "summary" in data
    assert "reflections" in data
    assert isinstance(data["reflections"], list)
    assert len(data["reflections"]) == 3
