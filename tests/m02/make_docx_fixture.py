#!/usr/bin/env python3
"""Build tests/m02/fixtures/library/03_TCVN/TCVN-FAKE-8888-2022.docx (deterministic, stored zip).

Run once from the repo root; the result is committed and its SHA-256 recorded in INDEX.yaml.
  uv run --no-project --python 3.11 tests/m02/make_docx_fixture.py
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "fixtures" / "library" / "03_TCVN" / "TCVN-FAKE-8888-2022.docx"
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def p(text: str) -> str:
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def table(rows: list[list[str]]) -> str:
    trs = "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in rows)
    return f"<w:tbl>{trs}</w:tbl>"


BODY = "".join([
    p("TCVN FAKE 8888:2022 — CÁP ĐIỆN GIẢ LẬP (FIXTURE M02, DOCX)"),
    p("1 Phạm vi"),
    p("Tiêu chuẩn giả lập về chọn cáp, định dạng DOCX."),
    p("2 Tiết diện cáp"),
    p("2.1 Tiết diện tối thiểu"),
    p("Tiết diện giả lập tối thiểu của dây pha là 8,8 mm2."),
    p("2.2 Bảng chọn cáp"),
    p("Bảng 2 - Dòng điện giả lập"),
    table([["Tiết diện", "Dòng"], ["8,8", "88 A"]]),
    "<w:p><w:r><w:drawing/></w:r></w:p>",
    p("3 Hết"),
])
FILES = {
    "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/></Types>',
    "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>',
    "word/document.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}>'
        f"<w:body>{BODY}</w:body></w:document>",
}

if __name__ == "__main__":
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in FILES.items():
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zf.writestr(zi, data.encode("utf-8"))
    print(OUT)
