"""Static checks for INDEX source paths (relative, '/'-separated, no escape, Windows-safe)."""
from __future__ import annotations

import re

from .textnorm import nfc

WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)


def relpath_problems(rel: str) -> list[str]:
    """Return why an INDEX path is unsafe; empty list means it may be joined to the source root."""
    problems = []
    if not isinstance(rel, str) or not rel:
        return ["empty path"]
    if rel != nfc(rel):
        problems.append("path is not NFC-normalized")
    if "\x00" in rel:
        problems.append("NUL character")
    if "\\" in rel:
        problems.append("backslash separator (use '/')")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or rel.startswith("//"):
        problems.append("absolute path")
    if ":" in rel:
        problems.append("':' not allowed (drive letter or alternate data stream)")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            problems.append(f"segment {part!r} not allowed")
        elif part != part.rstrip(" ."):
            problems.append(f"segment {part!r} ends with space or dot")
        elif WINDOWS_RESERVED.match(part):
            problems.append(f"segment {part!r} is a reserved Windows device name")
        if any(ord(c) < 32 for c in part):
            problems.append("control character")
    return sorted(set(problems))
