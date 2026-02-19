# Changelog

All notable changes to this project will be documented in this file.

## 0.2.3
- feat: CLI `--version` flag
- chore: add pre-commit (black/ruff) and normalize LF line endings

docs/quick-start
=======

main
## 0.2.2 — 2025-01-XX
- feat(cli): add `--no-emoji` flag to disable emoji in status output
- feat(encoding): automatic encoding detection for UTF-8, UTF-8 BOM, UTF-16 LE/BE
- feat(parser): improved JSON input validation with clear error messages
- feat(cli): clear, actionable error messages for decode/JSON issues
- feat(tests): comprehensive test coverage for encodings, stdin, globbing, multi-file outputs
- feat(ci): matrix CI with ubuntu-latest, windows-latest, macos-latest on Python 3.10-3.12
- feat(dev): pre-commit hooks and .editorconfig for consistent code formatting
- docs: Windows-specific notes for PowerShell encoding and command chaining
- docs: troubleshooting section for common encoding and JSON issues

## 0.1.6 — version bump to match latest release
- glob support + strict exit codes from 0.1.5
- stdout/pretty flags from 0.1.4

## 0.1.1 — 2025-08-07
- fix(parser): read files with utf-8-sig to strip UTF-8 BOM
- docs: Quickstart is path-agnostic; add CI/Release badges
