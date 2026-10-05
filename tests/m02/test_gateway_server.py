#!/usr/bin/env python3
"""M02 MCP surface: the stdio server exposes exactly three tools, no raw NotebookLM/mutation tools,
and the NotebookLM transport client fails closed. Runs real subprocesses, offline."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CANARY, FIXTURES, REPO, TODAY

from gateway.adapters.notebooklm import M01_READ_TOOLS, McpStdioNotebookLMClient
from gateway.errors import GatewayError

PUBLIC = ["standards_lookup", "standards_verify", "standards_status"]
RAW_NOTEBOOKLM = {"notebook_list", "notebook_get", "source_get_content", "notebook_query", "notebook_delete",
                  "notebook_create", "source_add", "source_delete", "notebook_share_public", "studio_create",
                  "research_start", "save_auth_tokens"}


class StdioServer:
    def __init__(self, config: Path):
        self.proc = subprocess.Popen([sys.executable, "-m", "gateway.server", "--config", str(config)],
                                     cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.id = 0

    def rpc(self, method, params=None):
        self.id += 1
        self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": self.id, "method": method,
                                           "params": params or {}}) + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline().decode("utf-8"))

    def close(self) -> str:
        self.proc.stdin.close()
        self.proc.wait(timeout=20)
        err = self.proc.stderr.read().decode("utf-8")
        self.proc.stdout.close()
        self.proc.stderr.close()
        return err


class McpSurface(unittest.TestCase):
    def setUp(self):
        self.srv = StdioServer(FIXTURES / "gateway.fixture.json")
        init = self.srv.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "m02-test", "version": "1"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")

    def tearDown(self):
        if not getattr(self, "closed", False):
            self.srv.close()

    def test_tools_list_is_exactly_three_gateway_tools(self):
        tools = self.srv.rpc("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], PUBLIC)
        self.assertFalse({t["name"] for t in tools} & RAW_NOTEBOOKLM)
        for t in tools:
            self.assertNotIn("$ref", json.dumps(t["inputSchema"]))
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_raw_notebooklm_and_mutation_tools_are_unknown(self):
        for name in sorted(RAW_NOTEBOOKLM):
            res = self.srv.rpc("tools/call", {"name": name, "arguments": {}})["result"]
            self.assertTrue(res["isError"], name)
            self.assertIn("Unknown tool", res["content"][0]["text"])

    def test_lookup_call_and_structured_invalid_request(self):
        res = self.srv.rpc("tools/call", {"name": "standards_lookup", "arguments": {
            "query": "HD FAKE INJECTION mục 2", "work_code": "GEN-FAKE", "assessment_date": TODAY}})["result"]
        self.assertFalse(res["isError"])
        self.assertEqual(res["structuredContent"]["status"], "FOUND")
        self.assertIn(CANARY, res["structuredContent"]["results"][0]["EVIDENCE"]["text"])
        bad = self.srv.rpc("tools/call", {"name": "standards_lookup", "arguments": {"query": 5}})["result"]
        self.assertTrue(bad["isError"])
        self.assertEqual(bad["structuredContent"]["error"]["code"], "INVALID_REQUEST")
        st = self.srv.rpc("tools/call", {"name": "standards_status", "arguments": {}})["result"]
        self.assertEqual(st["structuredContent"]["components"]["notebooklm"]["state"], "disabled")

    def test_stderr_logs_carry_no_query_or_source_text(self):
        self.srv.rpc("tools/call", {"name": "standards_lookup", "arguments": {
            "query": "HD FAKE INJECTION mục 2 câu hỏi riêng tư", "work_code": "GEN-FAKE", "assessment_date": TODAY}})
        err = self.srv.close()
        self.closed = True
        for line in err.splitlines():
            json.loads(line)
        for secret in (CANARY, "riêng tư", "notebook_delete", "HD FAKE INJECTION"):
            self.assertNotIn(secret, err)


class Transport(unittest.TestCase):
    """McpStdioNotebookLMClient against offline stand-ins of the M01 gated server."""

    def make_config(self, script: Path) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        cfg = Path(self.tmp.name) / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {
            "command": sys.executable, "args": [str(script)]}}}), encoding="utf-8")
        return cfg

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def test_four_tool_server_is_accepted_and_only_read_tools_are_callable(self):
        client = McpStdioNotebookLMClient(self.make_config(REPO / "tests" / "m01" / "selftest_fake_notebooklm.py"))
        try:
            self.assertEqual(client.notebook_list()["status"], "success")
            q = client.notebook_query("selftest-notebook", "x", ["selftest-injection-source"])
            self.assertEqual(q["status"], "success")
            with self.assertRaises(GatewayError) as cm:
                client._tool("notebook_delete", {"notebook_id": "x", "confirm": True})
            self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED")
        finally:
            client.close()

    def test_server_exposing_extra_tools_is_refused(self):
        src = (REPO / "tests" / "m01" / "selftest_fake_notebooklm.py").read_text(encoding="utf-8")
        widened = src.replace('TOOLS = [', 'TOOLS = [\n    {"name": "notebook_delete", "description": "x", '
                                          '"inputSchema": {"type": "object"}},', 1)
        self.assertNotEqual(src, widened)
        tmp = tempfile.TemporaryDirectory()
        try:
            script = Path(tmp.name) / "widened_fake.py"
            script.write_text(widened, encoding="utf-8")
            (Path(tmp.name) / "fixtures").mkdir()
            (Path(tmp.name) / "fixtures" / "M01-10_injection_source.md").write_text("x", encoding="utf-8")
            client = McpStdioNotebookLMClient(self.make_config(script))
            with self.assertRaises(GatewayError) as cm:
                client.notebook_list()
            self.assertEqual(cm.exception.code, "BACKEND_UNAVAILABLE")
            self.assertIn("four M01-approved", cm.exception.message)
            client.close()
        finally:
            tmp.cleanup()

    def test_read_tool_constant_matches_m01_policy(self):
        policy = (REPO / "config" / "m01-tool-policy.yaml").read_text(encoding="utf-8")
        block = policy.split("allowed_tools:")[1].split("\n\n")[0]
        self.assertEqual(sorted(M01_READ_TOOLS), sorted(l.strip("- ").strip() for l in block.splitlines()
                                                         if l.strip().startswith("- ")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
