#!/usr/bin/env python3
"""M03 D5: tests for validate_repo_metadata.py. The real checkout passes, and each check has negative controls.

Each negative control works on a temporary Git repository that holds a copy of the tracked files the checks read.
The test breaks exactly one condition, commits nothing (the file stays tracked) and asserts that exactly that check
reports FAIL while the others stay PASS. The real checkout is never modified. No network, no NotebookLM.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import validate_repo_metadata as vm  # noqa: E402

REPO = vm.REPO
NB = "mcp__gemini-notebook-mcp__"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, timeout=60)


class RepoCopy:
    """The tracked files the six checks read, copied into a fresh temporary Git repository (git add only)."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="m03-metadata-")
        self.root = Path(self._tmp.name)
        files = vm.tracked(REPO, "*.json", "*INDEX*.yaml", "config/m01-tool-policy.yaml")
        for rel in files:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, dst)
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")

    def path(self, rel: str) -> Path:
        return self.root / rel

    def edit_json(self, rel: str, fn) -> None:
        p = self.path(rel)
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        fn(data)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, rel: str, text: str) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        git(self.root, "add", "--", rel)

    def results(self) -> dict:
        return {r["name"]: r for r in vm.run_checks(self.root)}

    def close(self) -> None:
        self._tmp.cleanup()


class RealCheckout(unittest.TestCase):
    def test_real_checkout_passes_every_check(self):
        results = vm.run_checks(REPO)
        self.assertEqual([r["name"] for r in results], list(vm.CHECKS))
        for r in results:
            self.assertEqual(r["result"], "PASS", f"{r['name']}: {r['problems']}")

    def test_cli_exit_code(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(vm.main(["--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS")


class NegativeControls(unittest.TestCase):
    def setUp(self):
        self.copy = RepoCopy()
        self.addCleanup(self.copy.close)

    def assertOnlyFails(self, name: str, needle: str) -> None:
        results = self.copy.results()
        for other, r in results.items():
            if other == name:
                self.assertEqual(r["result"], "FAIL", f"{name} should FAIL")
                self.assertTrue(any(needle in p for p in r["problems"]), r["problems"])
            else:
                self.assertEqual(r["result"], "PASS", f"{other} should stay PASS: {r['problems']}")

    def test_baseline_copy_passes(self):
        for name, r in self.copy.results().items():
            self.assertEqual(r["result"], "PASS", f"{name}: {r['problems']}")

    # GATEWAY_CONFIGS_VALID_AND_DISABLED
    def test_config_mode_mcp_stdio_fails(self):
        self.copy.edit_json("tests/m02/fixtures/gateway.fixture.json",
                            lambda d: d["notebooklm"].__setitem__("mode", "mcp_stdio"))
        self.assertOnlyFails("GATEWAY_CONFIGS_VALID_AND_DISABLED", "not 'disabled'")

    def test_config_mode_missing_fails(self):
        self.copy.edit_json("docs/m02-pilot/gateway.pilot.stage-b.json", lambda d: d["notebooklm"].pop("mode"))
        self.assertOnlyFails("GATEWAY_CONFIGS_VALID_AND_DISABLED", "not 'disabled'")

    def test_config_schema_invalid_fails(self):
        self.copy.edit_json("docs/m02-pilot/gateway.pilot.stage-a.json", lambda d: d.__setitem__("unexpected", 1))
        self.assertOnlyFails("GATEWAY_CONFIGS_VALID_AND_DISABLED", "config.v1.json")

    def test_no_config_tracked_fails(self):
        for rel in vm.tracked(self.copy.root, "*.json"):
            data = json.loads(self.copy.path(rel).read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and data.get("schema") == vm.CONFIG_SCHEMA:
                git(self.copy.root, "rm", "-q", "-f", "--", rel)
        self.assertOnlyFails("GATEWAY_CONFIGS_VALID_AND_DISABLED", "no tracked")

    # INDEX_FILES_VALID
    def test_broken_index_fails(self):
        self.copy.path("tests/m02/fixtures/INDEX.yaml").write_text("schema: [unclosed\n", encoding="utf-8")
        self.assertOnlyFails("INDEX_FILES_VALID", "tests/m02/fixtures/INDEX.yaml")

    def test_template_that_loads_fails(self):
        shutil.copyfile(self.copy.path("tests/m02/fixtures/INDEX.yaml"),
                        self.copy.path("docs/m02-pilot/INDEX.pilot.template.yaml"))
        self.assertOnlyFails("INDEX_FILES_VALID", "template must fail closed")

    # M01_SERVER_PIN
    def test_pin_changed_fails(self):
        def bump(d):
            args = d["mcpServers"]["gemini-notebook-mcp"]["args"]
            args[args.index("notebooklm-mcp-cli==0.15.1")] = "notebooklm-mcp-cli==0.15.2"
        self.copy.edit_json(".mcp.json", bump)
        self.assertOnlyFails("M01_SERVER_PIN", "not started as uvx")

    def test_extra_enabled_tool_fails(self):
        def widen(d):
            env = d["mcpServers"]["gemini-notebook-mcp"]["env"]
            env["NOTEBOOKLM_ENABLED_TOOLS"] += ",source_add"
        self.copy.edit_json(".mcp.json", widen)
        self.assertOnlyFails("M01_SERVER_PIN", "four M01 read tools")

    # M01_POLICY_CONSISTENT
    def test_settings_allow_extra_tool_fails(self):
        self.copy.edit_json(".claude/settings.json", lambda d: d["permissions"]["allow"].append(NB + "source_add"))
        self.assertOnlyFails("M01_POLICY_CONSISTENT", ".claude/settings.json")

    def test_policy_allowed_tools_changed_fails(self):
        p = self.copy.path("config/m01-tool-policy.yaml")
        text = p.read_text(encoding="utf-8")
        self.assertIn("  - notebook_query\n", text)
        p.write_text(text.replace("  - notebook_query\n", "  - notebook_query\n  - source_add\n", 1), encoding="utf-8")
        self.assertOnlyFails("M01_POLICY_CONSISTENT", "allowed_tools")

    # GATEWAY_NOT_IN_PROJECT_MCP
    def test_gateway_server_in_project_mcp_fails(self):
        gw = json.loads((REPO / "tests/m02/fixtures/gateway.mcp.json").read_text(encoding="utf-8"))
        self.copy.edit_json(".mcp.json", lambda d: d["mcpServers"].update(gw["mcpServers"]))
        self.assertOnlyFails("GATEWAY_NOT_IN_PROJECT_MCP", vm.GATEWAY_SERVER)

    def test_gateway_server_under_other_name_fails(self):
        gw = json.loads((REPO / "tests/m02/fixtures/gateway.mcp.json").read_text(encoding="utf-8"))
        self.copy.edit_json(".mcp.json",
                            lambda d: d["mcpServers"].__setitem__("renamed", gw["mcpServers"][vm.GATEWAY_SERVER]))
        self.assertOnlyFails("GATEWAY_NOT_IN_PROJECT_MCP", "runs gateway.server")

    # SCHEMAS_PARSE
    def test_invalid_schema_json_fails(self):
        self.copy.add("gateway/schemas/broken.v1.json", "{ not json")
        self.assertOnlyFails("SCHEMAS_PARSE", "not valid JSON")

    def test_schema_without_id_or_title_fails(self):
        self.copy.add("gateway/schemas/anonymous.v1.json", json.dumps({"type": "object"}))
        self.assertOnlyFails("SCHEMAS_PARSE", "no $id or title")


if __name__ == "__main__":
    unittest.main()
