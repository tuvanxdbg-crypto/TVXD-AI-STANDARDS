#!/usr/bin/env python3
"""Offline stand-in for `uvx`: runs the command after `--` as a child that shares this process's stdin/stdout,
appends the child's pid to --pid-file, waits for it and exits with its code. Contacts no service.

It reproduces the process tree of the real server (uvx.exe -> python notebooklm-mcp), so tests can check that a
teardown kills and verifies the whole tree, not only the process the Gateway started (F14).
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid-file", required=True)
    ap.add_argument("--child-new-session", action="store_true",
                    help="start the child outside this process's group/job (an escape the Gateway must refuse)")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
    extra = {}
    if args.child_new_session:
        extra = ({"creationflags": 0x01000000} if sys.platform == "win32"   # CREATE_BREAKAWAY_FROM_JOB
                 else {"start_new_session": True})
    child = subprocess.Popen(cmd, stdin=sys.stdin, stdout=sys.stdout, **extra)
    with open(args.pid_file, "a", encoding="utf-8") as fh:
        fh.write(f"{child.pid}\n")
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
