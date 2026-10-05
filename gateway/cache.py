"""In-memory evidence cache (per Gateway process).

The key covers the normalized request and context, the resolved source identities
(document, version, INDEX sha256 of the file, NotebookLM mapping + sync identity),
the INDEX file hash and the INDEX/rules versions. Any change gives a different key.
A hit is still re-validated by the service against the current INDEX and, for local
evidence, the current file hash before it is returned; a failed revalidation evicts
the entry. The cache never bypasses whitelist, applicability or drift checks.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict


class EvidenceCache:
    def __init__(self, max_entries: int = 256):
        self.max_entries = max_entries
        self._data: OrderedDict[str, dict] = OrderedDict()
        self.hits = self.misses = self.evictions = self.invalidations = 0

    @staticmethod
    def key(material: dict) -> str:
        blob = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        if key in self._data:
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, key: str, value: dict) -> None:
        if self.max_entries <= 0:
            return
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)
            self.evictions += 1

    def invalidate(self, key: str) -> None:
        if self._data.pop(key, None) is not None:
            self.invalidations += 1

    def invalidate_index(self, index_sha256: str) -> None:
        """Drop entries built from a different INDEX file."""
        for k in [k for k, v in self._data.items() if v.get("index_sha256") != index_sha256]:
            del self._data[k]
            self.invalidations += 1

    def stats(self) -> dict:
        return {"entries": len(self._data), "max_entries": self.max_entries, "hits": self.hits,
                "misses": self.misses, "evictions": self.evictions, "invalidations": self.invalidations}
