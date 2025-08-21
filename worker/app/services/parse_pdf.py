def extract_text_from_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError("pypdf is required to parse PDF files. Install with: pip install pypdf") from e
    reader = PdfReader(path)
    out = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            out.append(text)
    return "\n".join(out)
