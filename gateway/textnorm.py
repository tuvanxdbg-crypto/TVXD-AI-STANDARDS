"""Unicode helpers: NFC for storage/compare, a folded key for diacritic-insensitive matching."""
from __future__ import annotations

import re
import unicodedata


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def letters(s: str) -> str:
    """Case- and accent-insensitive key that keeps đ distinct from d ("Điểm đ" -> "điem đ").

    đ is a separate letter of the Vietnamese alphabet (U+0111 has no decomposition), so
    identifiers such as the points "d)" and "đ)" must be compared with this key, not fold().
    """
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().casefold()


def fold(s: str) -> str:
    """Case- and diacritic-insensitive matching key for keywords ("Điều 5" -> "dieu 5"; đ -> d)."""
    return letters(s).replace("đ", "d")


def squash_ws(s: str) -> str:
    return re.sub(r"\s+", " ", nfc(s)).strip()


def tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-z]+", fold(s)) if len(t) >= 2 or t.isdigit()]
