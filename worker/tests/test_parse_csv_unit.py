import csv
from app.services.parse_csv import extract_text_from_csv


def test_extract_text_from_csv(tmp_path):
    p = tmp_path / "s.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "age"])
        w.writerow(["alice", "30"])
    text = extract_text_from_csv(str(p))
    assert "name | age" in text
    assert "alice | 30" in text
