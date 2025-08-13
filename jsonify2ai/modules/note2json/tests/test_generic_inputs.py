import subprocess
import sys
import os
import json
from pathlib import Path


def run_cli(args, stdin_input=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "note_to_json.cli", *args],
        input=stdin_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_stdin_json_autodetect_normalizes():
    payload = '{"foo":1,"title":"x"}'
    result = run_cli(
        ["--stdin", "--input-format", "auto", "--stdout"], stdin_input=payload
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    out = result.stdout.strip()
    assert out, "Expected JSON on stdout"
    data = json.loads(out)
    for key in ["title", "raw_text", "plain_text"]:
        assert key in data, f"Missing key: {key}"


def test_txt_file_parses_plain_text(tmp_path: Path):
    note_path = tmp_path / "note.txt"
    note_path.write_text("just a raw note", encoding="utf-8")
    result = run_cli([str(note_path), "--stdout"])
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    data = json.loads(result.stdout.strip())
    assert "title" in data
    assert "note" in data["title"].lower()


def test_stdin_wins_over_files(tmp_path: Path):
    dummy = tmp_path / "dummy.md"
    dummy.write_text("# ignore me", encoding="utf-8")
    payload = '{"from":"stdin"}'
    result = run_cli(
        ["--stdin", "--input-format", "auto", "--stdout", str(dummy)],
        stdin_input=payload,
    )
    assert result.returncode == 0
    assert "Warning: --stdin provided; ignoring file paths" in result.stderr
    data = json.loads(result.stdout.strip())
    assert data["raw_text"] == '{"from":"stdin"}'
