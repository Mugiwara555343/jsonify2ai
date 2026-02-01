# Note to JSON

[![PyPI version](https://img.shields.io/pypi/v/note-to-json.svg)](https://pypi.org/project/note-to-json/)
[![Python versions](https://img.shields.io/pypi/pyversions/note-to-json.svg)](https://pypi.org/project/note-to-json/)
[![License](https://img.shields.io/pypi/l/note-to-json.svg)](LICENSE)
[![CI](https://github.com/Mugiwara555343/note2json/actions/workflows/python-ci.yml/badge.svg)](https://github.com/Mugiwara555343/note2json/actions/workflows/python-ci.yml)
[![Publish](https://github.com/Mugiwara555343/note2json/actions/workflows/publish.yml/badge.svg)](https://github.com/Mugiwara555343/note2json/actions/workflows/publish.yml)
[![Build](https://img.shields.io/github/actions/workflow/status/Mugiwara555343/note-to-json-demo/python-ci.yml?branch=main&logo=github&label=build)](#)

Convert Markdown or text files to structured JSON, offline.

## Features

- **Privacy-first**: All processing happens locally, no data sent to external services
- **Flexible input**: Supports Markdown, plain text, and JSON files
- **Automatic encoding detection**: Handles UTF-8, UTF-16, and other encodings
- **Batch processing**: Process multiple files with glob patterns
- **Resilient parsing**: Graceful handling of malformed inputs and encoding issues
- **Progress reporting**: Detailed feedback for batch operations
- **Error recovery**: Continue processing even when some files fail

## Installation

```bash
pip install note-to-json
```

## 🚀 Quick Start

Install in a virtual environment (Windows PowerShell shown):
```powershell
python -m venv vtest
vtest\Scripts\activate
pip install --upgrade pip
pip install note-to-json

Check version:

note2json --version

Convert a Markdown file to JSON:

Set-Content note.md "# hello" -Encoding utf8
note2json note.md --stdout --pretty

Parse JSON inputs as well:

Set-Content obj.json '{"note":"Already JSON"}' -Encoding utf8
note2json obj.json --input-format json --stdout

## CLI Usage

### Basic Commands

```bash
note2json [OPTIONS] INPUT_FILE(S)
```

### Options

- `-o, --output PATH`: Specify output file path
- `--stdout`: Print JSON to STDOUT instead of writing to file
- `--pretty`: Pretty-print JSON with 2-space indentation
- `--stdin`: Read input from STDIN instead of files
- `--input-format {auto,md,txt,json}`: Specify input format (default: auto)
- `--no-emoji`: Disable emoji in status output
- `--continue-on-error`: Continue processing remaining files even if some fail
- `--verbose`: Show detailed progress information
- `--retry-failed`: Automatically retry failed files with different strategies

### Input Formats

- **auto** (default): Automatically detect format based on content
- **md/txt**: Parse as Markdown/plain text
- **json**: Parse as JSON (with schema validation)

### Examples

```bash
# Parse to default output file
note2json input.md                    # → input.parsed.json

# Parse to custom output file
note2json input.md -o output.json     # → output.json

# Parse to STDOUT
note2json input.md --stdout           # → prints to terminal

# Pretty-print to STDOUT
note2json input.md --stdout --pretty  # → formatted JSON

# Process multiple files
note2json *.md                        # → individual .parsed.json files

# Continue on errors
note2json *.md --continue-on-error    # → process all files, report failures

# Retry failed files automatically
note2json *.md --retry-failed         # → retry failed files with different strategies

# Show progress
note2json *.md --verbose              # → detailed progress information

# Read from STDIN (Windows)
type data.json | note2json --stdin --input-format json --stdout

# Read from STDIN (macOS/Linux)
cat data.json | note2json --stdin --input-format json --stdout
```

## Resilience Features

### Error Handling

The CLI provides robust error handling with clear, actionable error messages:

- **Encoding issues**: Automatic fallback to multiple encoding detection methods
- **Malformed inputs**: Graceful degradation with automatic validation fixes
- **Batch processing**: Continue processing even when individual files fail
- **Detailed reporting**: Comprehensive error summaries with categorization
- **Actionable advice**: Specific suggestions for fixing common issues
- **Retry strategies**: Automatic retry with different parsing approaches

### Error Types

- **Missing files**: Exit code 2
- **Parsing errors**: Exit code 3
- **Encoding errors**: Detailed information about attempted encodings
- **Validation errors**: Automatic fixing of common schema issues
- **Format mismatches**: Clear guidance on input format selection
- **Retry failures**: Information when all retry strategies fail

### Enhanced Error Messages

Error messages now include specific, actionable advice:

```bash
# Example of enhanced error message with advice
Error: Schema validation failed at 'title': 'None' is not of type 'string'
💡 Advice: Add the missing required field 'title'
```

### Retry Logic

Use `--retry-failed` to automatically attempt processing failed files with different strategies:

```bash
note2json *.md --retry-failed
```

The retry system will:
1. **Format switching**: Try different input formats (txt, json, auto)
2. **Raw text processing**: Fall back to basic text extraction
3. **Schema relaxation**: Create minimal valid structures when possible
4. **Detailed reporting**: Show which retry strategy succeeded

### Continue on Error

Use `--continue-on-error` to process all files even when some fail:

```bash
note2json *.md --continue-on-error
```

This will:
- Process all files that can be parsed
- Report failures with detailed error messages
- Provide a summary of successful vs. failed files
- Exit with appropriate error code

### Enhanced Progress Reporting

Use `--verbose` for detailed progress information with time estimation:

```bash
note2json *.md --verbose
```

Shows:
- Current file being processed
- Progress counter (e.g., [3/10])
- Visual progress bar with percentage
- Estimated time remaining (ETA)
- Summary of results
- Error breakdown by type
- Troubleshooting tips for common issues

## Output Schema

The tool outputs structured JSON with the following schema:

```json
{
  "title": "string",
  "timestamp": "ISO 8601 date-time",
  "raw_text": "string",
  "plain_text": "string",
  "tags": ["string"],
  "headers": ["string"],
  "date": "string (optional)",
  "tone": "string (optional)",
  "summary": "string (optional)",
  "reflections": ["string (optional)"]
}
```

## Input Format Support

### Markdown/Text

- **Headers**: Extracts `# Title` as headers
- **Metadata**: Parses `**Date:**`, `**Tags:**`, `**Tone:**` fields
- **Summary**: Extracts content between `**Summary:**` and `---`
- **Reflections**: Extracts bullet points after `**Core Reflections:**`

### JSON

- **Schema validation**: Ensures output matches required schema
- **Auto-normalization**: Converts arbitrary JSON to schema format
- **Format detection**: Automatically identifies JSON vs. text content

## Encoding Support

- **UTF-8**: Standard encoding with BOM support
- **UTF-16**: Little-endian and big-endian variants
- **Fallback detection**: Uses chardet for automatic encoding detection
- **Error handling**: Graceful degradation with detailed error reporting

## Development

### Installation

```bash
git clone https://github.com/Mugiwara555343/note2json.git
cd note2json
pip install -e .
```

### Testing

```bash
# Run all tests
pytest

# Run integration tests only
pytest -m integration

# Run with coverage
pytest --cov=note_to_json
```

### Code Quality

```bash
# Format code
black note_to_json/ tests/

# Sort imports
isort note_to_json/ tests/

# Run pre-commit hooks
pre-commit run --all-files
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Changelog

### v0.2.2

- **Resilience improvements**: Better error handling and recovery
- **Continue on error**: Process remaining files even when some fail
- **Progress reporting**: Detailed feedback for batch operations
- **Enhanced encoding detection**: Fallback mechanisms and better error messages
- **Validation fixes**: Automatic correction of common schema issues
- **Error categorization**: Grouped error reporting for better analysis

### v0.2.1

- Improved encoding detection
- Better error messages
- Enhanced JSON passthrough

### v0.2.0

- Added JSON input support
- Improved encoding handling
- Better error reporting

### v0.1.0

- Initial release
- Basic Markdown parsing
- CLI interface
