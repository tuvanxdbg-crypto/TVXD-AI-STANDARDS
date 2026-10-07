#!/usr/bin/env python3
"""Synthetic stand-in for the stage-A pilot sources, for dry runs of the pilot scripts (no real content).

Writes three fake DOCX files with the pilot file names into OUT/library, a copy of the pilot INDEX with their
hashes, and a copy of the stage-A config pointing at them. The 8794 stand-in starts with a table of contents,
so its clause IDs 1 and 5 occur twice, as in the real file. The real pilot folder is never read.

  uv run --no-project --python 3.11 tests/m02/make_pilot_synthetic.py <empty OUT dir>
  ... tests/m02/pilot_stage_a.py discover --config <OUT>/gateway.pilot.stage-a.json --out <OUT>/evidence
"""
import hashlib, json, sys, zipfile
from pathlib import Path
from xml.sax.saxutils import escape
repo = Path(__file__).resolve().parents[2]; out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
lib = out / "library"; lib.mkdir(exist_ok=True)
def p(t): return f'<w:p><w:r><w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:p>'
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def docx(path, paras):
    files = {"[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
             "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
             "word/document.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(p(x) for x in paras)}</w:body></w:document>'}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for n, d in files.items():
            zi = zipfile.ZipInfo(n, (2020, 1, 1, 0, 0, 0)); z.writestr(zi, d)
docs = {
 "2025-LUAT-135-QH15-Xay-dung.docx": ["LUẬT GIẢ LẬP", "Chương I", "QUY ĐỊNH CHUNG", "Điều 1. Phạm vi giả lập", "Nội dung giả lập điều 1.", "Điều 2. Đối tượng giả lập", "1. Khoản giả lập.", "a) Điểm giả lập."],
 "2024-TCVN-5575-Thiet-ke-ket-cau-thep.docx": ["TCVN GIẢ LẬP KẾT CẤU", "1 Phạm vi áp dụng", "Nội dung giả lập.", "2 Tài liệu viện dẫn", "Danh mục giả lập."],
 "2011-TCVN-8794-Truong-trung-hoc-yeu-cau-th.docx": ["TCVN GIẢ LẬP TRƯỜNG", "Mục lục", "1 Phạm vi áp dụng", "5 Yêu cầu thiết kế", "1 Phạm vi áp dụng", "Nội dung giả lập.", "5 Yêu cầu thiết kế", "5.1 Chiếu sáng lớp học", "Yêu cầu giả lập về chiếu sáng lớp học trường trung học."],
}
idx = (repo / "docs/m02-pilot/INDEX.pilot.draft.yaml").read_text(encoding="utf-8")
for name, paras in docs.items():
    docx(lib / name, paras)
    real = None
    for line in idx.splitlines():
        if name in line:
            real = line.split('sha256: "')[1].split('"')[0]
    idx = idx.replace(real, hashlib.sha256((lib / name).read_bytes()).hexdigest())
(out / "INDEX.pilot.draft.yaml").write_text(idx, encoding="utf-8")
cfg = json.loads((repo / "docs/m02-pilot/gateway.pilot.stage-a.json").read_text())
cfg["source_root"] = "library"
(out / "gateway.pilot.stage-a.json").write_text(json.dumps(cfg), encoding="utf-8")
print(out / "gateway.pilot.stage-a.json")
# Stage B stand-in: the same mapping as INDEX.pilot.stage-b.yaml, re-pointed at the synthetic hashes.
sb = (repo / "docs/m02-pilot/INDEX.pilot.stage-b.yaml").read_text(encoding="utf-8")
for name in docs:
    real = next(ln.split('sha256: "')[1].split('"')[0] for ln in sb.splitlines() if name in ln)
    sb = sb.replace(real, hashlib.sha256((lib / name).read_bytes()).hexdigest())
(out / "INDEX.pilot.stage-b.yaml").write_text(sb, encoding="utf-8")
cfg_b = json.loads((repo / "docs/m02-pilot/gateway.pilot.stage-b.json").read_text())
cfg_b["source_root"] = "library"
cfg_b["notebooklm"]["mcp_config"] = str(repo / ".mcp.json")
(out / "gateway.pilot.stage-b.json").write_text(json.dumps(cfg_b), encoding="utf-8")
