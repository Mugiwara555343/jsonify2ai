import subprocess
import pytest
import os
from pathlib import Path
import tempfile
import json


@pytest.mark.integration
def test_cli_integration():
    """Test that the note2json CLI works end-to-end"""
    # Get a demo file to test with
    demo_file = Path(__file__).parent.parent / "demo_entries" / "demo_entry.md"

    if not demo_file.exists():
        pytest.skip("Demo file not found")

    # Create a temporary output file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        tmp_json = Path(tmp_file.name)

    try:
        # Run the CLI command with UTF-8 environment
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            ["note2json", str(demo_file), "-o", str(tmp_json)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        # Assert the command succeeded
        assert (
            result.returncode == 0
        ), f"CLI failed with return code {result.returncode}. stderr: {result.stderr}"

        # Assert the output file was created
        assert tmp_json.exists(), f"Output file {tmp_json} was not created"

        # Optional: verify the JSON is valid
        import json

        with open(tmp_json, "r") as f:
            data = json.load(f)
            assert "title" in data
            assert "timestamp" in data

    finally:
        # Clean up the temporary file
        if tmp_json.exists():
            tmp_json.unlink()


@pytest.mark.integration
def test_cli_stdout_flag():
    """Test that the --stdout flag works correctly"""
    # Get a demo file to test with
    demo_file = Path(__file__).parent.parent / "demo_entries" / "demo_entry.md"

    if not demo_file.exists():
        pytest.skip("Demo file not found")

    # Run the CLI command with --stdout flag
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        ["note2json", str(demo_file), "--stdout"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )

    # Assert the command succeeded with exit code 0
    assert (
        result.returncode == 0
    ), f"CLI failed with return code {result.returncode}. stderr: {result.stderr}"

    # Assert STDOUT contains valid JSON
    assert result.stdout.strip(), "STDOUT should not be empty"

    # Parse the JSON and verify it has the required fields
    try:
        data = json.loads(result.stdout.strip())
        assert "title" in data, "JSON should contain 'title' field"
        assert "timestamp" in data, "JSON should contain 'timestamp' field"
    except json.JSONDecodeError as e:
        pytest.fail(f"STDOUT should contain valid JSON: {e}")


@pytest.mark.integration
def test_cli_missing_file_exit_code():
    """Test that missing files return exit code 2"""
    # Run the CLI command with a clearly missing path
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        ["note2json", "definitely_missing_file.md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )

    # Assert the command failed with exit code 2
    assert (
        result.returncode == 2
    ), f"CLI should return exit code 2 for missing files, got {result.returncode}"

    # Assert STDERR contains "File not found"
    assert (
        "Error: File not found:" in result.stderr
    ), f"STDERR should contain 'File not found', got: {result.stderr}"


@pytest.mark.integration
def test_cli_glob_expansion():
    """Test that glob patterns are expanded correctly"""
    # Get demo files to test with
    demo_dir = Path(__file__).parent.parent / "demo_entries"
    demo_files = list(demo_dir.glob("*.md"))

    if len(demo_files) < 2:
        pytest.skip("Need at least 2 demo files for glob test")

    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Copy demo files to temp directory
        for i, demo_file in enumerate(demo_files[:2]):
            temp_file = temp_path / f"test_{i}.md"
            temp_file.write_text(demo_file.read_text(), encoding="utf-8")

        # Run the CLI command with glob pattern
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            ["note2json", str(temp_path / "*.md"), "--stdout"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

        # Assert the command succeeded
        assert (
            result.returncode == 0
        ), f"CLI failed with return code {result.returncode}. stderr: {result.stderr}"

        # Assert STDOUT contains multiple JSON objects (one per line)
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2, f"Should have at least 2 JSON objects, got {len(lines)}"

        # Verify each line is valid JSON with title field
        for line in lines:
            if line.strip():  # Skip empty lines
                try:
                    data = json.loads(line)
                    assert (
                        "title" in data
                    ), "Each JSON object should contain 'title' field"
                except json.JSONDecodeError as e:
                    pytest.fail(f"Each line should be valid JSON: {e}")
