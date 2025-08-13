# Contributing to note-to-json

Thanks for wanting to help. Keep it simple, keep it shippable.

## Quick Setup

```bash
# 1) Fork + clone your fork, then:
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 2) Dev install
pip install -e ".[dev]"       # uses pyproject.toml extras

# 3) Run tests
pytest -q
```

### Windows tips
- Use PowerShell backticks for newlines inside strings: `` `n ``
- File encodings: the parser reads **utf-8-sig** to handle BOM safely.

## Running the CLI locally

```bash
note2json demo.md -o out.json
note2json *.md --stdout | jq
echo {"a":1} | note2json --stdin --input-format auto --stdout
```

## Coding Guidelines
- Keep functions small, pure, and covered by tests.
- Prefer explicit flags over magic behavior.
- Exit codes: `0=ok`, `2=missing input`, `3=parse failure`.

## Tests
- Put tests in `tests/` using `pytest`.
- Add a minimal integration test when you touch the CLI wiring.
- Run locally:
  ```bash
  pytest -q
  ```

## Commits & PRs
- Conventional messages (example):
  - `feat(cli): add --stdin`
  - `fix(parser): strip BOM on Windows`
  - `docs(readme): add quickstart`
- Small PRs with a short “what/why” and before/after examples are best.
- Update README if behavior or flags change.

## Release Process (maintainers)
- Bump version in `pyproject.toml` (semver).
- Tag the release: `git tag vX.Y.Z -m "..." && git push origin vX.Y.Z`
- **Publishing** is done via GitHub Actions (Trusted Publisher) to TestPyPI/PyPI.
- Update GitHub Release notes (copy changelog highlights + install line).

## Security
- This tool runs locally and offline. If you find a parsing or execution risk,
  open a private issue or email the maintainer.
