# scripts/validate_json.py
from __future__ import annotations

import sys
import json
import pathlib
from typing import Iterable, Tuple, Dict, List

# --- bootstrap sys.path so imports never fail ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worker.app.schema.chunk_schema import Chunk, is_deterministic_id  # noqa: E402


def iter_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    if root.is_file():
        if root.suffix.lower() in {".json", ".jsonl"}:
            yield root
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".json", ".jsonl"}:
            yield p


def load_chunks(p: pathlib.Path) -> Iterable[Tuple[pathlib.Path, Dict]]:
    if p.suffix.lower() == ".jsonl":
        with p.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield p, json.loads(line)
                except Exception as e:
                    raise SystemExit(f"[jsonl-parse-error] {p}:{i} {e}")
    else:
        with p.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                raise SystemExit(f"[json-parse-error] {p} {e}")
        if isinstance(data, list):
            for obj in data:
                yield p, obj
        else:
            raise SystemExit(f"[json-structure-error] {p} expected array of chunks")


def check_strict_constraints(chunks: List[Chunk]) -> List[str]:
    errs: List[str] = []
    by_doc: Dict[str, List[int]] = {}
    for c in chunks:
        by_doc.setdefault(c.document_id, []).append(c.idx)
    for doc, idxs in by_doc.items():
        s = sorted(idxs)
        if not s:
            continue
        expected = list(range(s[0], s[-1] + 1))
        if s != expected:
            errs.append(
                f"[idx-gap] document_id={doc} got_first15={s[:15]} expected_consecutive"
            )
    for c in chunks:
        if not is_deterministic_id(c):
            errs.append(
                f"[id-not-deterministic] doc={c.document_id} idx={c.idx} id={c.id[:12]}…"
            )
    return errs


def run(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Validate chunk JSON/JSONL files.")
    ap.add_argument("path", help="file or directory")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.path)
    if not root.exists():
        print(f"[path-missing] {root}", file=sys.stderr)
        return 3

    files = list(iter_files(root))
    total = 0
    ok = 0
    errors: List[str] = []
    materialized: List[Chunk] = []

    for file in files:
        for p, obj in load_chunks(file):
            total += 1
            try:
                c = Chunk.model_validate(obj)
                materialized.append(c)
                ok += 1
            except Exception as e:
                errors.append(f"[schema-error] {p} :: {str(e).splitlines()[0]}")
                if len(errors) >= 10:
                    break
        if len(errors) >= 10:
            break

    if args.strict and not errors:
        errors.extend(check_strict_constraints(materialized)[:10])

    if not args.quiet:
        print(
            f"[validate] files_scanned={len(files)} chunks={total} ok={ok} errors={len(errors)} strict={args.strict}"
        )

    if errors and not args.quiet:
        for e in errors:
            print(" -", e)

    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
