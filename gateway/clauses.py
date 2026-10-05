"""Clause structure for the two INDEX clause schemes.

numeric  TCVN/QCVN style headings: a line that starts with a dotted number and text,
         optionally after markdown '#': "2 Text", "2.1 Text", "2.1.3. Text". Ids are the
         number. "1. text" (single number with a dot) is a list item unless after '#'.
article  Vietnamese legal style: "Chương II", "Điều 5." (article), inside an article
         "2." (khoản) and inside a khoản "a)" (điểm).
         Ids: "Điều 5", "Điều 5 khoản 2", "Điều 5 khoản 2 điểm a".
Matching of keywords is diacritic-insensitive; returned headings keep the source text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .textnorm import fold

NUMERIC_HEAD = re.compile(r"^\s*(#{1,6}\s*)?(\d{1,3}(?:\.\d{1,3}){0,5})(\.?)\s+(\S.*)$")
CHAPTER = re.compile(r"^\s*(?:#{1,6}\s*)?chuong\s+([ivxlcdm]+|\d+)\b")
ARTICLE = re.compile(r"^\s*(?:#{1,6}\s*)?dieu\s+(\d{1,4}[a-z]?)\b")
KHOAN = re.compile(r"^\s*(\d{1,3})\.\s+\S")
DIEM = re.compile(r"^\s*([a-z])\)\s+\S")


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    start: int   # 0-based first line (the heading)
    end: int     # exclusive
    level: int


def parse_sections(lines: tuple[str, ...], scheme: str) -> list[Section]:
    return _numeric(lines) if scheme == "numeric" else _article(lines)


def _close(heads: list[tuple[str, str, int, int]], n: int) -> list[Section]:
    out = []
    for i, (sid, heading, start, level) in enumerate(heads):
        end = n
        for sid2, _h, start2, level2 in heads[i + 1:]:
            if level2 <= level:
                end = start2
                break
        out.append(Section(sid, heading, start, end, level))
    return out


def _numeric(lines: tuple[str, ...]) -> list[Section]:
    heads = []
    for i, ln in enumerate(lines):
        m = NUMERIC_HEAD.match(ln)
        if not m:
            continue
        num, dotted = m.group(2), m.group(3)
        if dotted and "." not in num and not m.group(1):
            continue  # "1. item" is a list item unless it is a markdown heading
        heads.append((num, ln.strip().lstrip("#").strip(), i, num.count(".") + 1))
    return _close(heads, len(lines))


def _article(lines: tuple[str, ...]) -> list[Section]:
    heads = []
    article = khoan = None
    for i, ln in enumerate(lines):
        f = fold(ln)
        if CHAPTER.match(f):
            heads.append((f"Chương {CHAPTER.match(f).group(1).upper()}", ln.strip().lstrip("#").strip(), i, 0))
            article = khoan = None
        elif ARTICLE.match(f):
            article, khoan = ARTICLE.match(f).group(1), None
            heads.append((f"Điều {article}", ln.strip().lstrip("#").strip(), i, 1))
        elif article and KHOAN.match(ln):
            khoan = KHOAN.match(ln).group(1)
            heads.append((f"Điều {article} khoản {khoan}", ln.strip(), i, 2))
        elif article and khoan and DIEM.match(f):
            heads.append((f"Điều {article} khoản {khoan} điểm {DIEM.match(f).group(1)}", ln.strip(), i, 3))
    return _close(heads, len(lines))


def canonical_clause(ref: str, scheme: str, *, strict: bool = True) -> str | None:
    """Normalize a clause reference. strict=False also scans free query text."""
    f = fold(ref)
    if scheme == "numeric":
        pat = r"^(?:muc|dieu|khoan|clause|section)?\s*(\d{1,3}(?:\.\d{1,3}){0,5})$" if strict else \
            r"(?:muc|dieu|khoan|clause|section)\s+(\d{1,3}(?:\.\d{1,3}){0,5})(?![0-9.])"
        m = re.search(pat, f)
        return m.group(1) if m else None
    art = re.search(r"dieu\s+(\d{1,4}[a-z]?)\b", f)
    if not art:
        return None
    out = f"Điều {art.group(1)}"
    kh = re.search(r"khoan\s+(\d{1,3})\b", f)
    if kh:
        out += f" khoản {kh.group(1)}"
        dm = re.search(r"diem\s+([a-z])\b", f)
        if dm:
            out += f" điểm {dm.group(1)}"
    if strict and re.sub(r"(dieu|khoan|diem)\s+[0-9a-z]+", "", f).strip(" ,.;"):
        return None
    return out
