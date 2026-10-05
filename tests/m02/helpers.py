"""Shared helpers for the M02 offline tests (standard library + PyYAML)."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from gateway.config import load_config  # noqa: E402
from gateway.logs import JsonLogger  # noqa: E402
from gateway.service import GatewayService  # noqa: E402

TODAY = "2026-10-05"
FIXED_NOW = dt.datetime(2026, 10, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
CANARY = "TVXD-M02-CANARY-5D1E"


def tree_digest(root: Path) -> dict[str, str]:
    """SHA-256 of every file under root (relative POSIX path -> digest), incl. names and links."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            out[rel] = "link:" + os.readlink(p)
        elif p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class FixtureCopy:
    """A throwaway copy of tests/m02/fixtures so tests may change INDEX/files safely."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="m02-fixture-")
        self.root = Path(self._tmp.name) / "fixtures"
        shutil.copytree(FIXTURES, self.root, symlinks=True)

    @property
    def config(self) -> Path:
        return self.root / "gateway.fixture.json"

    @property
    def index(self) -> Path:
        return self.root / "INDEX.yaml"

    @property
    def library(self) -> Path:
        return self.root / "library"

    def edit_index(self, old: str, new: str, count: int = 1) -> None:
        text = self.index.read_text(encoding="utf-8")
        assert text.count(old) >= count, f"{old!r} not found in INDEX"
        self.index.write_text(text.replace(old, new, count), encoding="utf-8")

    def cleanup(self) -> None:
        self._tmp.cleanup()


def make_service(config: Path | None = None, *, client=None, **kw) -> tuple[GatewayService, io.StringIO]:
    logs = io.StringIO()
    svc = GatewayService(load_config(config or FIXTURES / "gateway.fixture.json"), notebooklm_client=client,
                         now=lambda: FIXED_NOW, logger=JsonLogger(stream=logs, level="debug"), backoff_s=0.0, **kw)
    return svc, logs


def lookup(svc: GatewayService, **args) -> dict:
    return svc.call("standards_lookup", args)


def log_records(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
