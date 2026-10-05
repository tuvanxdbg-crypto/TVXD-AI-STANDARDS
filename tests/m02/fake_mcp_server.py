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
    return 0


if __name__ == "__main__":
    sys.exit(main())
