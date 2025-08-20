from docx import Document
from app.services.parse_docx import extract_text_from_docx

def test_extract_text_from_docx(tmp_path):
    p = tmp_path / "s.docx"
    doc = Document()
    doc.add_paragraph("Hello world")
    row = doc.add_table(rows=1, cols=2).rows[0]
    row.cells[0].text, row.cells[1].text = "A", "B"
    doc.save(p)
    txt = extract_text_from_docx(str(p))
    assert "Hello world" in txt
    assert "A" in txt and "B" in txt
