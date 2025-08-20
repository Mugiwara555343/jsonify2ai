import csv

def extract_text_from_csv(path: str, max_rows: int = 5000) -> str:
    """
    Read CSV/TSV and return a simple line-based text:
    header: "col1 | col2", rows: "v1 | v2".
    """
    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel  # fallback
        reader = csv.reader(f, dialect)
        out = []
        for i, row in enumerate(reader):
            line = " | ".join((cell or "").strip() for cell in row)
            out.append(line)
            if i >= max_rows:
                break
    return "\n".join(out)
