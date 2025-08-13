#!/usr/bin/env python3
"""
note_to_json.cli

Command-line interface for the note-to-json parser.
"""
from . import __version__
import argparse
import glob
import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from . import __version__
from .parser import read_input, ParsingError
from .utils import read_text_safely, read_stdin_safely
import time
from datetime import datetime


class ProcessingResult:
    """Container for processing results with metadata."""

    def __init__(
        self,
        input_path: Path,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
    ):
        self.input_path = input_path
        self.success = success
        self.data = data
        self.error = error
        self.error_type = error_type

    def __str__(self):
        if self.success:
            return f"✅ {self.input_path.name}"
        else:
            return f"❌ {self.input_path.name}: {self.error}"


def expand_glob_patterns(patterns: List[str]) -> List[str]:
    """Expand glob patterns and return sorted, deduplicated list of files."""
    expanded_files = []

    for pattern in patterns:
        # Check if pattern contains glob characters
        if any(char in pattern for char in ["*", "?", "["]):
            # Use recursive=True if pattern contains '**'
            recursive = "**" in pattern
            try:
                matched_files = glob.glob(pattern, recursive=recursive)
                if not matched_files:
                    # If glob pattern matches nothing, treat as missing file
                    expanded_files.append(pattern)
                else:
                    expanded_files.extend(matched_files)
            except Exception as e:
                # Handle glob pattern errors gracefully
                print(
                    f"Warning: Invalid glob pattern '{pattern}': {e}", file=sys.stderr
                )
                expanded_files.append(pattern)
        else:
            # No glob characters, treat as literal path
            expanded_files.append(pattern)

    # Deduplicate and sort for deterministic order
    return sorted(set(expanded_files))


def process_single_file(
    input_path: Path, input_format: str, no_emoji: bool = False
) -> ProcessingResult:
    """Process a single file and return a ProcessingResult."""
    try:
        # Read file with automatic encoding detection
        text = read_text_safely(input_path)
        filename_hint = input_path.stem
        parsed_data = read_input(text, input_format, filename_hint=filename_hint)
        return ProcessingResult(input_path, True, data=parsed_data)

    except ParsingError as e:
        # Handle parsing errors with clear messages and actionable advice
        if input_format == "json":
            error_msg = "Invalid JSON input. If this is Markdown or text, use `--input-format md|txt`."
            error_type = "format_mismatch"
        else:
            error_msg = str(e)
            error_type = getattr(e, "error_type", "parsing_error")

            # Add actionable advice for validation errors
            if hasattr(e, "context") and e.context and "advice" in e.context:
                error_msg += f"\n💡 Advice: {e.context['advice']}"

        return ProcessingResult(
            input_path, False, error=error_msg, error_type=error_type
        )

    except ValueError as e:
        # Handle encoding errors with detailed information
        error_msg = str(e)
        if "Decoding error" in str(e):
            error_type = "encoding_error"
        else:
            error_type = "value_error"
        return ProcessingResult(
            input_path, False, error=error_msg, error_type=error_type
        )

    except Exception as e:
        return ProcessingResult(
            input_path, False, error=str(e), error_type="unexpected_error"
        )


def retry_failed_file(
    input_path: Path, original_error: str, no_emoji: bool = False
) -> ProcessingResult:
    """Retry processing a failed file with different strategies."""
    if no_emoji:
        print(
            f"  Retrying {input_path.name} with different strategies...",
            file=sys.stderr,
        )
    else:
        print(
            f"  🔄 Retrying {input_path.name} with different strategies...",
            file=sys.stderr,
        )

    # Strategy 1: Try with different input format if it was auto-detected
    try:
        text = read_text_safely(input_path)
        # Try forcing text format if it might be markdown
        if input_path.suffix.lower() in [".md", ".markdown", ".txt"]:
            parsed_data = read_input(text, "txt", filename_hint=input_path.stem)
            if no_emoji:
                return ProcessingResult(
                    input_path,
                    True,
                    data=parsed_data,
                    error="Retry successful with txt format",
                )
            else:
                return ProcessingResult(
                    input_path,
                    True,
                    data=parsed_data,
                    error="🔄 Retry successful with txt format",
                )
    except Exception:
        pass

    # Strategy 2: Try with JSON format if it might be JSON
    try:
        text = read_text_safely(input_path)
        if input_path.suffix.lower() in [".json"]:
            parsed_data = read_input(text, "json", filename_hint=input_path.stem)
            if no_emoji:
                return ProcessingResult(
                    input_path,
                    True,
                    data=parsed_data,
                    error="Retry successful with json format",
                )
            else:
                return ProcessingResult(
                    input_path,
                    True,
                    data=parsed_data,
                    error="🔄 Retry successful with json format",
                )
    except Exception:
        pass

    # Strategy 3: Try with raw text processing (more lenient)
    try:
        text = read_text_safely(input_path)
        # Create minimal valid data structure
        parsed_data = {
            "title": input_path.stem or "untitled",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "raw_text": text[:1000] + ("..." if len(text) > 1000 else ""),
            "plain_text": text[:1000].replace("\n", " ")
            + ("..." if len(text) > 1000 else ""),
            "tags": [],
            "headers": [],
            "reflections": [],
        }
        if no_emoji:
            return ProcessingResult(
                input_path,
                True,
                data=parsed_data,
                error="Retry successful with raw text processing",
            )
        else:
            return ProcessingResult(
                input_path,
                True,
                data=parsed_data,
                error="🔄 Retry successful with raw text processing",
            )
    except Exception:
        pass

    # All retry strategies failed
    return ProcessingResult(
        input_path,
        False,
        error=f"All retry strategies failed. Original error: {original_error}",
        error_type="retry_failed",
    )


def process_stdin(
    input_format: str, no_emoji: bool = False
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Process STDIN input and return parsed data and optional error."""
    try:
        # Read from STDIN with automatic encoding detection
        text = read_stdin_safely(sys.stdin.buffer)
        parsed_data = read_input(text, input_format, filename_hint="stdin")
        return parsed_data, None
    except (ValueError, ParsingError) as e:
        return {}, str(e)
    except Exception as e:
        return {}, f"Failed to parse STDIN: {e}"


def print_progress(
    current: int,
    total: int,
    filename: str,
    no_emoji: bool = False,
    start_time: Optional[float] = None,
):
    """Print progress information for batch operations with enhanced details."""
    percentage = (current / total) * 100 if total > 0 else 0

    if no_emoji:
        progress_bar = (
            f"[{'=' * int(percentage / 5)}{' ' * (20 - int(percentage / 5))}]"
        )
        print(
            f"Processing [{current}/{total}] {progress_bar} {percentage:.1f}%: {filename}",
            file=sys.stderr,
        )
    else:
        progress_bar = (
            f"[{'🟦' * int(percentage / 5)}{'⬜' * (20 - int(percentage / 5))}]"
        )

        # Add time estimation if start_time is provided
        time_info = ""
        if start_time and current > 1:
            elapsed = time.time() - start_time
            avg_time_per_file = elapsed / (current - 1)
            remaining_files = total - current
            estimated_remaining = avg_time_per_file * remaining_files

            if estimated_remaining > 60:
                time_info = f" (ETA: {estimated_remaining/60:.1f}m)"
            else:
                time_info = f" (ETA: {estimated_remaining:.1f}s)"

        print(
            f"🔄 [{current}/{total}] {progress_bar} {percentage:.1f}%: {filename}{time_info}",
            file=sys.stderr,
        )


def print_summary(results: List[ProcessingResult], no_emoji: bool = False):
    """Print a summary of processing results with enhanced error analysis."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if no_emoji:
        print(
            f"\nSummary: {len(successful)} successful, {len(failed)} failed",
            file=sys.stderr,
        )
    else:
        print(
            f"\n📊 Summary: {len(successful)} successful, {len(failed)} failed",
            file=sys.stderr,
        )

    if failed:
        print("\nFailed files:", file=sys.stderr)
        for result in failed:
            if no_emoji:
                print(f"  ❌ {result.input_path.name}: {result.error}", file=sys.stderr)
            else:
                print(f"  ❌ {result.input_path.name}: {result.error}", file=sys.stderr)

        # Group errors by type for better analysis
        error_types = {}
        for result in failed:
            error_type = result.error_type or "unknown"
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(result.input_path.name)

        if len(error_types) > 1:
            print("\nError breakdown:", file=sys.stderr)
            for error_type, files in error_types.items():
                if no_emoji:
                    print(f"  {error_type}: {len(files)} files", file=sys.stderr)
                else:
                    print(f"  🔍 {error_type}: {len(files)} files", file=sys.stderr)

        # Provide specific advice for common error types
        print("\nTroubleshooting tips:", file=sys.stderr)
        if "encoding_error" in error_types:
            if no_emoji:
                print(
                    "  • For encoding errors: Re-save files as UTF-8 or use --stdin",
                    file=sys.stderr,
                )
            else:
                print(
                    "  💡 For encoding errors: Re-save files as UTF-8 or use --stdin",
                    file=sys.stderr,
                )

        if "format_mismatch" in error_types:
            if no_emoji:
                print(
                    "  • For format errors: Use --input-format to specify the correct format",
                    file=sys.stderr,
                )
            else:
                print(
                    "  💡 For format errors: Use --input-format to specify the correct format",
                    file=sys.stderr,
                )

        if "validation_error" in error_types or "missing_required_field" in error_types:
            if no_emoji:
                print(
                    "  • For validation errors: Check that files have required title and content",
                    file=sys.stderr,
                )
            else:
                print(
                    "  💡 For validation errors: Check that files have required title and content",
                    file=sys.stderr,
                )

        if "parsing_error" in error_types:
            if no_emoji:
                print(
                    "  • For parsing errors: Ensure files contain valid content (not empty)",
                    file=sys.stderr,
                )
            else:
                print(
                    "  💡 For parsing errors: Ensure files contain valid content (not empty)",
                    file=sys.stderr,
                )


def determine_exit_code(
    results: List[ProcessingResult], missing_files: List[Path]
) -> int:
    """Determine appropriate exit code based on results."""
    if missing_files:
        return 2  # Missing files
    elif any(not r.success for r in results):
        return 3  # Parsing errors
    return 0  # Success


def main():
    """Main CLI entry point with improved resilience."""
    parser = argparse.ArgumentParser(
        description="Convert markdown/text or JSON inputs to structured JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  note2json input.md                    # Parse to input.parsed.json
  note2json input.md -o output.json     # Parse to custom output file
  note2json input.md --stdout           # Print JSON to STDOUT
  note2json input.md --stdout --pretty  # Pretty-print JSON to STDOUT
  note2json *.md                        # Parse multiple files
  note2json *.md --continue-on-error    # Continue processing even if some files fail

  # Read from STDIN (Windows):
  type data.json | note2json --stdin --input-format json --stdout

  # Read from STDIN (macOS/Linux):
  cat data.json | note2json --stdin --input-format json --stdout
        """,
    )

    parser.add_argument(
        "input_file",
        nargs="*",
        help="Input file(s) to parse (supports glob patterns like *.md, **/*.md)",
    )

    parser.add_argument(
        "-o", "--output", help="Output file path (default: input.parsed.json)"
    )

    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to STDOUT instead of writing to file",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with 2-space indentation",
    )

    parser.add_argument(
        "--stdin", action="store_true", help="Read input from STDIN instead of files"
    )

    parser.add_argument(
        "--input-format",
        choices=["auto", "md", "txt", "json"],
        default="auto",
        help="Input format: auto-detect (default), md, txt, or json",
    )

    parser.add_argument(
        "--no-emoji", action="store_true", help="Disable emoji in status output"
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining files even if some fail",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed progress information"
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed files with different parsing strategies",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the note2json version and exit",
    )

    args = parser.parse_args()

    # Handle conflict between --stdout and -o/--output
    if args.stdout and args.output:
        print("Warning: --stdout overrides -o/--output", file=sys.stderr)

    # Centralize status output
    ok_prefix = "✅ " if not args.no_emoji else ""

    # If --stdin is provided, prefer it over file paths
    if args.stdin:
        if args.input_file:
            print("Warning: --stdin provided; ignoring file paths", file=sys.stderr)

        parsed_data, error = process_stdin(args.input_format, args.no_emoji)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)

        indent = 2 if args.pretty else None
        if args.stdout or not args.output:
            json.dump(parsed_data, sys.stdout, indent=indent, ensure_ascii=False)
            if not args.pretty:
                print()
        else:
            output_path = Path(args.output)
            output_path.write_text(
                json.dumps(parsed_data, indent=indent, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"{ok_prefix}Parsed: STDIN → {output_path.name}")
        sys.exit(0)

    # No --stdin: need at least one file
    if not args.input_file:
        print("Error: No input provided. Use files or --stdin.", file=sys.stderr)
        sys.exit(2)

    # Expand glob patterns
    input_files = expand_glob_patterns(args.input_file)

    # Track missing files and processing results
    missing_files = []
    processing_results = []

    # Process each input file
    start_time = time.time() if args.verbose else None

    for i, input_path_str in enumerate(input_files):
        input_path = Path(input_path_str)

        if args.verbose:
            print_progress(
                i + 1, len(input_files), input_path.name, args.no_emoji, start_time
            )

        if not input_path.exists():
            missing_files.append(input_path)
            if not args.continue_on_error:
                print(f"Error: File not found: {input_path}", file=sys.stderr)
                continue
            else:
                print(
                    f"Warning: File not found: {input_path} (continuing...)",
                    file=sys.stderr,
                )
                continue

        result = process_single_file(input_path, args.input_format, args.no_emoji)
        processing_results.append(result)

        # Handle immediate failures if not continuing on error
        if not result.success and not args.continue_on_error:
            if result.error_type == "format_mismatch":
                print(f"Error: {result.error}", file=sys.stderr)
            elif result.error_type == "encoding_error":
                print(
                    f"Error: Encoding issue with {input_path.name}: {result.error}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: Failed to parse {input_path.name}: {result.error}",
                    file=sys.stderr,
                )
            sys.exit(3)

        # If retry is enabled and the file failed, try retry strategies
        if not result.success and args.retry_failed:
            retry_result = retry_failed_file(input_path, result.error, args.no_emoji)
            if retry_result.success:
                # Replace the failed result with the successful retry
                processing_results[-1] = retry_result
                if args.no_emoji:
                    print(
                        f"  ✅ Retry successful for {input_path.name}", file=sys.stderr
                    )
                else:
                    print(
                        f"  ✅ Retry successful for {input_path.name}", file=sys.stderr
                    )

    # Handle missing files
    for missing_file in missing_files:
        print(f"Error: File not found: {missing_file}", file=sys.stderr)

    # Print summary if verbose or if there were failures
    if args.verbose or any(not r.success for r in processing_results):
        print_summary(processing_results, args.no_emoji)

    # Determine exit code
    exit_code = determine_exit_code(processing_results, missing_files)

    # Determine JSON formatting
    indent = 2 if args.pretty else None

    # Handle output
    if args.stdout:
        # Print to STDOUT (NDJSON format for multiple files)
        successful_results = [r for r in processing_results if r.success]
        for i, result in enumerate(successful_results):
            if i > 0 and args.pretty:
                print()  # Add blank line between pretty-printed objects
            json.dump(result.data, sys.stdout, indent=indent, ensure_ascii=False)
            if not args.pretty:
                print()  # Add newline for compact format
    else:
        # Handle file output
        if args.output:
            if len(processing_results) > 1:
                print(
                    "Error: --output can only be used with a single input file",
                    file=sys.stderr,
                )
                sys.exit(1)
            elif len(processing_results) == 1:
                result = processing_results[0]
                if result.success:
                    output_path = Path(args.output)
                    output_path.write_text(
                        json.dumps(result.data, indent=indent, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(
                        f"{ok_prefix}Parsed: {result.input_path.name} → {output_path.name}"
                    )
                else:
                    print(
                        f"Error: Cannot write output for failed parse: {result.input_path.name}",
                        file=sys.stderr,
                    )
                    sys.exit(3)
        else:
            # Write individual output files
            for result in processing_results:
                if result.success:
                    output_path = result.input_path.with_suffix(".parsed.json")
                    output_path.write_text(
                        json.dumps(result.data, indent=indent, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(
                        f"{ok_prefix}Parsed: {result.input_path.name} → {output_path.name}"
                    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
