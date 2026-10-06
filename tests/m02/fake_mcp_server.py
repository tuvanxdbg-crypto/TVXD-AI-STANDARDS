#!/usr/bin/env python3
"""Offline MCP stdio stand-in for McpStdioNotebookLMClient startup tests. Contacts no service.

Options:
  --init-delay S     sleep S seconds before answering initialize
  --list-delay S     sleep S seconds before answering tools/list
  --delay-once FILE  apply the delays only while FILE does not exist (it is created on the first start)
  --call-delay S     sleep S seconds before answering tools/call (logged on receipt)
  --notify METHOD    before answering METHOD (initialize, tools/list or tools/call), stream
                     notifications/progress every --notify-every S for --notify-for S
  --extra-tool       also list notebook_delete (a surface the client must refuse)
  --log FILE         append "start" per process, "call <tool>" per tools/call received and
                     "cancelled <id>" per notifications/cancelled
  --times FILE       append "<unix time> <same event>" for the events above (timing checks)
  --stall-after-list S  after answering tools/list, stop reading stdin for S seconds
  --stall-once FILE  stall only while FILE does not exist (it is created on the first stall)
  --small-stdin-pipe shrink the stdin pipe to one page where the OS allows it (Linux F_SETPIPE_SZ),
                     so a few KB of unread input fill it, as with the small default pipes on Windows
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

READ_TOOLS = ["notebook_list", "notebook_get", "source_get_content", "notebook_query"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init-delay", type=float, default=0.0)
    ap.add_argument("--list-delay", type=float, default=0.0)
    ap.add_argument("--call-delay", type=float, default=0.0)
    ap.add_argument("--notify", choices=["initialize", "tools/list", "tools/call"])
    ap.add_argument("--notify-every", type=float, default=0.02)
    ap.add_argument("--notify-for", type=float, default=0.0)
    ap.add_argument("--delay-once")
    ap.add_argument("--extra-tool", action="store_true")
    ap.add_argument("--log")
    ap.add_argument("--times")
    ap.add_argument("--stall-after-list", type=float, default=0.0)
    ap.add_argument("--stall-once")
    ap.add_argument("--small-stdin-pipe", action="store_true")
    args = ap.parse_args()

    def log(line: str) -> None:
        if args.log:
            with open(args.log, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if args.times:
            with open(args.times, "a", encoding="utf-8") as fh:
                fh.write(f"{time.time():.6f} {line}\n")

    delays = True
    if args.delay_once:
        marker = Path(args.delay_once)
        delays = not marker.exists()
        marker.touch()
    if args.small_stdin_pipe:
        try:
            import fcntl
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETPIPE_SZ, 4096)
        except (ImportError, AttributeError, OSError):
            pass   # Windows: anonymous pipes are already small
    log("start")
    tools = READ_TOOLS + (["notebook_delete"] if args.extra_tool else [])

    def stream_notifications() -> None:
        end = time.monotonic() + args.notify_for
        while time.monotonic() < end:
            print(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress",
                              "params": {"progressToken": 1, "progress": 0}}), flush=True)
            time.sleep(args.notify_every)

    for raw in sys.stdin:
        msg = json.loads(raw)
        method, rid = msg.get("method"), msg.get("id")
        if method == "notifications/cancelled":
            log(f"cancelled {msg['params']['requestId']}")
        if rid is None:
            continue
        if method == "tools/call":
            log("call " + msg["params"]["name"])   # on receipt, before any delay or notification
        if method == args.notify:
            stream_notifications()
        if method == "initialize":
            if delays:
                time.sleep(args.init_delay)
            result = {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
                      "serverInfo": {"name": "fake-mcp", "version": "0"}}
        elif method == "tools/list":
            if delays:
                time.sleep(args.list_delay)
            result = {"tools": [{"name": t, "description": "fake", "inputSchema": {"type": "object"}} for t in tools]}
        elif method == "tools/call":
            time.sleep(args.call_delay)
            result = {"content": [{"type": "text", "text": json.dumps({"status": "success", "notebooks": []})}]}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown"}}),
                  flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
        if method == "tools/list" and args.stall_after_list:
            stall = True
            if args.stall_once:
                stall = not Path(args.stall_once).exists()
                Path(args.stall_once).touch()
            if stall:
                log("stall")
                time.sleep(args.stall_after_list)
                log("resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
