"""In-memory lookup cache (per Gateway process), contract v2.

The key covers the evidence contract and trust policy, the normalized request and context,
the queried NotebookLM scope (document, INDEX version, notebook id, source id per document),
the INDEX file hash and the INDEX/rules versions. Any change gives a different key, and an
entry built under another contract or policy can never be served for this one.

Since contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) the cache does not depend on local
file hashes, mappings to local files or sync proof, and a hit is not evidence that any source
was re-checked. Entries expire after `ttl_s` seconds (published in standards_status), and a
change of the INDEX file drops every entry built from the previous INDEX.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Callable


class EvidenceCache:
    def __init__(self, max_entries: int = 256, ttl_s: int = 3600, clock: Callable[[], float] = time.monotonic):
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.clock = clock
        self._data: OrderedDict[str, dict] = OrderedDict()
        self.hits = self.misses = self.evictions = self.invalidations = self.expirations = 0

    @staticmethod
    def key(material: dict) -> str:
        blob = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        entry = self._data.get(key)
        if entry is not None and self.clock() - entry["stored_at"] >= self.ttl_s:
            del self._data[key]
            self.expirations += 1
            entry = None
        if entry is None:
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return entry["value"]

    def put(self, key: str, value: dict) -> None:
        if self.max_entries <= 0 or self.ttl_s <= 0:
            return
        self._data[key] = {"stored_at": self.clock(), "value": value}
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)
            self.evictions += 1

    def invalidate(self, key: str) -> None:
        if self._data.pop(key, None) is not None:
            self.invalidations += 1

    def invalidate_index(self, index_sha256: str) -> None:
        """Drop entries built from a different INDEX file."""
        for k in [k for k, v in self._data.items() if v["value"].get("index_sha256") != index_sha256]:
            del self._data[k]
            self.invalidations += 1

    def stats(self) -> dict:
        return {"entries": len(self._data), "max_entries": self.max_entries, "ttl_s": self.ttl_s,
                "hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                "invalidations": self.invalidations, "expirations": self.expirations}
