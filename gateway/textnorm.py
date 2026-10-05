"""Unicode helpers: NFC for storage/compare, a folded key for diacritic-insensitive matching."""
from __future__ import annotations

import re
import unicodedata


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def fold(s: str) -> str:
    """Case- and diacritic-insensitive matching key ("Điều 5" -> "dieu 5")."""
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().casefold()


def squash_ws(s: str) -> str:
    return re.sub(r"\s+", " ", nfc(s)).strip()


def tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-z]+", fold(s)) if len(t) >= 2 or t.isdigit()]
