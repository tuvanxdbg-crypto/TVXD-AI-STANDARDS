"""Structured JSON-line logs on stderr (stdout carries the MCP protocol).

Only whitelisted keys are written. Query text, project context, source text,
answers, cookies/tokens and environment are never logged; the query is
represented by a short SHA-256 prefix for correlation only.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from typing import TextIO

ALLOWED = {"event", "request_id", "tool", "route", "adapter", "status", "error_code", "duration_ms",
           "evidence_ids", "cache", "attempts", "notebooklm_calls", "query_sha256", "results", "index_version"}
LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}


class JsonLogger:
    def __init__(self, stream: TextIO | None = None, level: str = "info"):
        self.stream = stream or sys.stderr
        self.level = LEVELS.get(level, 20)

    def log(self, level: str, **fields) -> None:
        if LEVELS.get(level, 20) < self.level:
            return
        record = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"), "level": level}
        record.update({k: v for k, v in fields.items() if k in ALLOWED})
        try:
            self.stream.write(json.dumps(record, ensure_ascii=True) + "\n")
            self.stream.flush()
        except (OSError, ValueError):
            pass
