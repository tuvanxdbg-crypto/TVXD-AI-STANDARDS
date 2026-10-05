"""Gateway configuration (JSON, schema config.v1.json). Paths are relative to the config file."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import schema
from .errors import GatewayError


@dataclass(frozen=True)
class Limits:
    max_source_bytes: int = 20 * 1024 * 1024
    max_excerpt_chars: int = 4000
    max_docx_uncompressed_bytes: int = 50 * 1024 * 1024


@dataclass(frozen=True)
class NotebookLMConfig:
    mode: str = "disabled"            # "disabled" | "mcp_stdio"
    mcp_config: Path | None = None    # project .mcp.json with the M01 gated server
    server: str = "gemini-notebook-mcp"
    timeout_s: float = 60.0
    max_attempts: int = 2
    total_budget_s: float = 120.0


@dataclass(frozen=True)
class Config:
    index_path: Path
    source_root: Path
    notebooklm: NotebookLMConfig = field(default_factory=NotebookLMConfig)
    cache_max_entries: int = 256
    limits: Limits = field(default_factory=Limits)
    log_level: str = "info"


def _expand(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise GatewayError("INVALID_REQUEST", f"config references unset environment variable {name}")
        return os.environ[name]
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, value)


def _path(base: Path, value: str) -> Path:
    p = Path(_expand(value))
    return p if p.is_absolute() else (base / p)


def load_config(path: str | Path) -> Config:
    cfg_path = Path(path).resolve()
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise GatewayError("INVALID_REQUEST", f"cannot read config {cfg_path.name}: {type(e).__name__}") from None
    problems = schema.check(data, "config.v1.json")
    if problems:
        raise GatewayError("INVALID_REQUEST", "config does not match config.v1.json", details={"problems": problems})
    base = cfg_path.parent
    nb = data.get("notebooklm", {})
    return Config(
        index_path=_path(base, data["index_path"]),
        source_root=_path(base, data["source_root"]),
        notebooklm=NotebookLMConfig(
            mode=nb.get("mode", "disabled"),
            mcp_config=_path(base, nb["mcp_config"]) if nb.get("mcp_config") else None,
            server=nb.get("server", "gemini-notebook-mcp"),
            timeout_s=float(nb.get("timeout_s", 60)),
            max_attempts=int(nb.get("max_attempts", 2)),
            total_budget_s=float(nb.get("total_budget_s", 120)),
        ),
        cache_max_entries=int(data.get("cache", {}).get("max_entries", 256)),
        limits=Limits(**data.get("limits", {})),
        log_level=data.get("logging", {}).get("level", "info"),
    )
