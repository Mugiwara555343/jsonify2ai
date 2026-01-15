#!/usr/bin/env python3
"""
Generate deterministic DOCX sample used by smoke tests.
Safe to run multiple times. Creates:
  data/dropzone/smoke_golden/mini.docx
"""

from pathlib import Path


def main():
    out = Path("data/dropzone/smoke_golden/mini.docx")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from docx import Document  # python-docx
    except Exception:
        raise SystemExit(
            "python-docx is required to generate mini.docx.\n"
            "Install via worker/requirements.txt or pip install python-docx."
        )
    doc = Document()
    doc.add_paragraph("Experience: one tiny line for smoke.")
    doc.save(out)
    print(f"[ok] wrote {out}")


if __name__ == "__main__":
    main()
