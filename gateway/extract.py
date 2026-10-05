"""Text extraction for supported source formats. Read-only; never writes.

Supported (v1):
  md, txt  UTF-8 (BOM allowed). Table rows ('|') and image references are marked
           layout-dependent.
  docx     word/document.xml paragraphs in order. Tables are flattened to
           '| cell | cell |' lines and images become '[IMAGE]'; both are marked
           layout-dependent. Headers/footers, footnotes, comments and tracked
           changes are not extracted. Zip size/entry/ratio limits apply; DTDs are refused.
Not supported: pdf, doc and anything else -> UNSUPPORTED_FORMAT (no guessed text).
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .errors import GatewayError
from .textnorm import nfc

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT_FORMATS = ("md", "txt")
SUPPORTED_FORMATS = ("md", "txt", "docx")
LAYOUT_LINE = re.compile(r"^\s*\||!\[|<img\b|\[IMAGE\]", re.I)


@dataclass(frozen=True)
class Extracted:
    lines: tuple[str, ...]
    layout_lines: frozenset[int]   # 0-based indexes of table/image lines


def extract(raw: bytes, fmt: str, *, max_docx_uncompressed: int) -> Extracted:
    if fmt in TEXT_FORMATS:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise GatewayError("EXTRACTION_FAILED", "source is not valid UTF-8") from None
        lines = tuple(nfc(text).splitlines())
    elif fmt == "docx":
        lines = tuple(_docx_lines(raw, max_docx_uncompressed))
    else:
        raise GatewayError("UNSUPPORTED_FORMAT", f"format {fmt!r} is not supported for extraction",
                           details={"supported": list(SUPPORTED_FORMATS)})
    return Extracted(lines, frozenset(i for i, ln in enumerate(lines) if LAYOUT_LINE.search(ln)))


def _docx_lines(raw: bytes, max_uncompressed: int) -> list[str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise GatewayError("EXTRACTION_FAILED", "docx is not a valid zip container") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > max_uncompressed:
            raise GatewayError("EXTRACTION_FAILED", "docx exceeds uncompressed size/entry limits")
        try:
            info = zf.getinfo("word/document.xml")
        except KeyError:
            raise GatewayError("EXTRACTION_FAILED", "docx has no word/document.xml") from None
        if info.compress_size and info.file_size / info.compress_size > 200:
            raise GatewayError("EXTRACTION_FAILED", "docx compression ratio exceeds limit")
        xml = zf.read(info)
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise GatewayError("EXTRACTION_FAILED", "docx XML contains a DTD; refused")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise GatewayError("EXTRACTION_FAILED", "docx XML is malformed") from None
    body = root.find(f"{W}body")
    if body is None:
        raise GatewayError("EXTRACTION_FAILED", "docx has no document body")
    out: list[str] = []
    for el in body:
        if el.tag == f"{W}p":
            out.append(_para(el))
        elif el.tag == f"{W}tbl":
            for tr in el.iter(f"{W}tr"):
                cells = [" ".join(_para(p) for p in tc.iter(f"{W}p")).strip() for tc in tr.iter(f"{W}tc")]
                out.append("| " + " | ".join(cells) + " |")
    return [nfc(s) for s in out]


def _para(p: ET.Element) -> str:
    parts = []
    for node in p.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append(" ")
        elif node.tag in (f"{W}drawing", f"{W}pict"):
            parts.append("[IMAGE]")
    return "".join(parts)
