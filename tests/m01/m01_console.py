"""Console output for the M01 scripts must never crash a run (V-12).

When stdout/stderr is a pipe on Windows (PowerShell capture, Claude Code Remote,
CI), Python encodes console text with the ANSI code page, usually cp1252, which
cannot encode Vietnamese. M01 evidence files are always written as UTF-8; only
the console copy is affected, so unencodable characters are printed as \\uXXXX
escapes instead of raising UnicodeEncodeError. The console encoding itself is
left unchanged, so the parent process decodes the output the way it expects.
"""
from __future__ import annotations

import sys


def safe_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
