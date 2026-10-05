#!/usr/bin/env python3
"""Offline stand-in for the NotebookLM MCP server, for harness self-tests only.

Exposes the four M01 tool names over MCP stdio and serves
tests/m01/fixtures/M01-10_injection_source.md as the content of source
"selftest-injection-source". notebook_query returns a fixed offline answer.
It never talks to Google. Results obtained with it validate the M01-10 harness
and the probe's console output, they are NOT M01 acceptance evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "M01-10_injection_source.md"
NB = {"id": "selftest-notebook", "title": "TVXD-M01-TEST (offline self-test)", "source_count": 1}
SRC = {"id": "selftest-injection-source", "title": "M01-10_injection_source.md"}


def schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    {"name": "notebook_list", "description": "List all notebooks.",
     "inputSchema": schema({"max_results": {"type": "integer"}}, [])},
    {"name": "notebook_get", "description": "Get notebook details with sources.",
     "inputSchema": schema({"notebook_id": {"type": "string"}}, ["notebook_id"])},
    {"name": "source_get_content", "description": "Get raw text content of a source (no AI processing).",
     "inputSchema": schema({"source_id": {"type": "string"}}, ["source_id"])},
    {"name": "notebook_query", "description": "Ask AI about EXISTING sources already in notebook.",
     "inputSchema": schema({"notebook_id": {"type": "string"}, "query": {"type": "string"}},
                           ["notebook_id", "query"])},
]


def call(name: str, args: dict) -> dict:
    if name == "notebook_list":
        return {"status": "success", "notebooks": [NB], "count": 1}
    if name == "notebook_get":
        return {"status": "success", "notebook": NB, "sources": [SRC]}
    if name == "source_get_content":
        if args.get("source_id") != SRC["id"]:
            return {"status": "error", "error": "source not found"}
        text = FIXTURE.read_text(encoding="utf-8")
        return {"status": "success", "content": text, "title": SRC["title"],
                "source_type": "pasted_text", "char_count": len(text)}
    if name == "notebook_query":
        return {"status": "success", "answer": "(offline self-test) Nguồn thử nghiệm M01-10, không phải tiêu chuẩn thật.",
                "sources_used": [SRC["id"]], "citations": {}}
    raise KeyError(name)


def main() -> None:
    # MCP stdio is UTF-8. Windows pipes default to cp1252, which cannot encode the
    # Vietnamese fixture (V-12).
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        if "id" not in msg:
            continue  # notification
        rid, method, params = msg["id"], msg.get("method"), msg.get("params", {})
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "tvxd-m01-selftest-fake", "version": "0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                payload = call(params["name"], params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
            except KeyError:
                result = {"content": [{"type": "text", "text": f"Unknown tool: '{params.get('name')}'"}],
                          "isError": True}
        elif method == "ping":
            result = {}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                         "error": {"code": -32601, "message": "method not found"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
