"""Read-only local source adapter over the configured source root (Nextcloud sync/mount).

Since contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) the Gateway service does not use this adapter: lookup,
verify and status read no local files. It stays for the historical stage-A tooling and keeps its confinement tests.

Security rules:
  * Callers never pass paths. Paths come from INDEX and must pass paths.relpath_problems.
  * Every path component below the root is lstat'ed: symlinks and Windows reparse
    points (junctions, mount points) are refused.
  * The resolved file must stay inside the resolved root (commonpath) and be a regular file.
  * The file is opened read-only ('rb'); the opened handle must be the same file that
    was checked (st_dev/st_ino), and its size must be within limits.
  * Nothing under the source root is ever written, renamed or deleted.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ..clauses import Section, parse_sections
from ..config import Limits
from ..errors import GatewayError
from ..extract import Extracted, extract
from ..index import Version
from ..paths import relpath_problems
from ..textnorm import squash_ws, tokens

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class LocalDoc:
    rel_path: str
    sha256: str
    size: int
    text: Extracted
    sections: tuple[Section, ...]


class LocalSourceAdapter:
    name = "local"

    def __init__(self, source_root: Path, limits: Limits):
        self.root_config = Path(source_root)
        self.limits = limits
        self.reads = 0

    # ------------------------------------------------------------------ paths
    def _root(self) -> Path:
        try:
            root = self.root_config.resolve(strict=True)
        except OSError:
            raise GatewayError("BACKEND_UNAVAILABLE", "local source root is not available") from None
        if not root.is_dir():
            raise GatewayError("BACKEND_UNAVAILABLE", "local source root is not a directory")
        return root

    def resolve(self, rel_path: str) -> Path:
        problems = relpath_problems(rel_path)
        if problems:
            raise GatewayError("SOURCE_NOT_ALLOWED", "INDEX path rejected", details={"problems": problems})
        root = self._root()
        current = root
        for part in rel_path.split("/"):
            current = current / part
            try:
                st = os.lstat(current)
            except FileNotFoundError:
                raise GatewayError("SOURCE_NOT_FOUND", "source file not found under the source root") from None
            except OSError:
                raise GatewayError("SOURCE_NOT_FOUND", "source path not accessible") from None
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                raise GatewayError("SOURCE_NOT_ALLOWED", "symlink/junction inside the source root is not allowed")
        real = Path(os.path.realpath(current))
        if os.path.normcase(os.path.commonpath([str(real), str(root)])) != os.path.normcase(str(root)):
            raise GatewayError("SOURCE_NOT_ALLOWED", "resolved path escapes the source root")
        if not stat.S_ISREG(os.lstat(real).st_mode):
            raise GatewayError("SOURCE_NOT_ALLOWED", "source is not a regular file")
        return real

    # ------------------------------------------------------------------ reads
    def read_bytes(self, rel_path: str) -> bytes:
        path = self.resolve(rel_path)
        before = os.lstat(path)
        if before.st_size > self.limits.max_source_bytes:
            raise GatewayError("EXTRACTION_FAILED", "source exceeds max_source_bytes")
        with open(path, "rb") as fh:
            opened = os.fstat(fh.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise GatewayError("SOURCE_DRIFT", "source file changed while it was being opened")
            data = fh.read(self.limits.max_source_bytes + 1)
        if len(data) > self.limits.max_source_bytes:
            raise GatewayError("EXTRACTION_FAILED", "source exceeds max_source_bytes")
        self.reads += 1
        return data

    def file_sha256(self, rel_path: str) -> str:
        return hashlib.sha256(self.read_bytes(rel_path)).hexdigest()

    def load(self, version: Version, *, verify_hash: bool = True) -> LocalDoc:
        """Read, hash and parse an INDEX version. Raises SOURCE_DRIFT if the hash differs."""
        raw = self.read_bytes(version.path)
        digest = hashlib.sha256(raw).hexdigest()
        if verify_hash and digest != version.sha256:
            raise GatewayError("SOURCE_DRIFT", f"{version.source_key}: file hash differs from INDEX",
                               details={"expected": version.sha256, "observed": digest})
        text = extract(raw, version.format, max_docx_uncompressed=self.limits.max_docx_uncompressed_bytes)
        return LocalDoc(version.path, digest, len(raw), text, tuple(parse_sections(text.lines, version.clause_scheme)))

    def status(self) -> dict:
        try:
            root = self._root()
        except GatewayError as e:
            return {"state": "unavailable", "error": e.code, "reads": self.reads}
        return {"state": "ok", "root_readable": os.access(root, os.R_OK), "reads": self.reads}


# ---------------------------------------------------------------------- doc helpers

def find_clauses(doc: LocalDoc, clause_id: str) -> list[Section]:
    """Every section with this ID. Real documents repeat IDs (a table of contents, numbered table rows),
    so callers must treat more than one match as ambiguous, never pick one."""
    return [s for s in doc.sections if s.id == clause_id]


def find_clause(doc: LocalDoc, clause_id: str) -> Section | None:
    """The section with this ID when it is unique; None when it is absent or occurs more than once."""
    hits = find_clauses(doc, clause_id)
    return hits[0] if len(hits) == 1 else None


def clause_occurrences(doc: LocalDoc, clause_id: str) -> int:
    return sum(1 for s in doc.sections if s.id == clause_id)


def section_text(doc: LocalDoc, start: int, end: int, max_chars: int) -> tuple[str, bool, bool]:
    lines = doc.text.lines[start:end]
    text = "\n".join(lines).strip("\n")
    layout = any(i in doc.text.layout_lines for i in range(start, end))
    if len(text) > max_chars:
        return text[:max_chars], True, layout
    return text, False, layout


def search_sections(doc: LocalDoc, query: str, limit: int) -> list[tuple[int, Section]]:
    """Heuristic heading/body token overlap. Results are candidates, never exact matches."""
    q = set(tokens(query))
    if not q:
        return []
    scored = []
    for s in doc.sections:
        heading = set(tokens(s.heading))
        body = set(tokens(" ".join(doc.text.lines[s.start:s.end])))
        score = 3 * len(q & heading) + len(q & body)
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], x[1].level, x[1].start))
    return scored[:limit]


def find_passage(doc: LocalDoc, passage: str) -> tuple[int, int] | None:
    """Locate a passage (whitespace-normalized, exact otherwise) -> (start_line, end_line_exclusive)."""
    needle = squash_ws(passage)
    if len(needle) < 12:
        return None
    joined, offsets = [], []
    pos = 0
    for i, ln in enumerate(doc.text.lines):
        s = squash_ws(ln)
        offsets.append((pos, i))
        joined.append(s)
        pos += len(s) + 1
    hay = " ".join(joined)
    at = hay.find(needle)
    if at < 0:
        # Diacritic-insensitive fallback is NOT used: a passage must match the authoritative text.
        return None
    end_at = at + len(needle)
    start_line = max(i for p, i in offsets if p <= at)
    end_line = max(i for p, i in offsets if p < end_at) + 1
    return start_line, end_line


def section_for_lines(doc: LocalDoc, start: int, end: int) -> Section | None:
    """Smallest section that contains the line range."""
    best = None
    for s in doc.sections:
        if s.start <= start and end <= s.end and (best is None or s.end - s.start < best.end - best.start):
            best = s
    return best


__all__ = ["LocalSourceAdapter", "LocalDoc", "find_clause", "find_clauses", "clause_occurrences", "section_text",
           "search_sections", "find_passage", "section_for_lines"]
