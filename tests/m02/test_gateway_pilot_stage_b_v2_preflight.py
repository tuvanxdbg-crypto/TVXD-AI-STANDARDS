#!/usr/bin/env python3
"""Contract-v2 stage-B preflight (pilot_stage_b_v2_preflight.py), offline: every check and its negative control, on
the synthetic stage-B stand-in (make_pilot_synthetic.py) with injected git, config and token facts. No Windows
call, no network, no local library."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HERE, REPO

import pilot_stage_b_v2_preflight as pf

HEAD = "a" * 40
CLEAN_TOKEN = {"elevated": False, "integrity_rid": 0x2000, "integrity": "Medium",
               "privileges": ["SeChangeNotifyPrivilege", "SeShutdownPrivilege"]}


class StageBV2Preflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="m02-v2-preflight-")
        cls.syn = Path(cls._tmp.name) / "syn"
        subprocess.run([sys.executable, str(HERE / "make_pilot_synthetic.py"), str(cls.syn)], check=True,
                       capture_output=True)
        cls.config = cls.syn / "gateway.pilot.stage-b.json"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_checks(self, *, head=HEAD, porcelain="", disabled=True, config=None, mcp_json=REPO / ".mcp.json",
                   token=None, expect=HEAD):
        def git_fn(*args):
            return head if args[0] == "rev-parse" else porcelain
        return pf.run_checks(config or self.config, expect, git_fn=git_fn, configs_disabled=lambda: disabled,
                             mcp_json=mcp_json, token_facts=(lambda: token) if token is not None else None)

    def result(self, checks, name):
        return next(c["result"] for c in checks if c["name"] == name)

    def test_all_pass_on_a_live_host_and_not_a_live_host_elsewhere(self):
        status, checks, facts = self.run_checks(token=CLEAN_TOKEN)
        self.assertEqual(status, "PASS", checks)
        self.assertEqual(facts["notebook"], "8ca84143-c240-4fcb-98fe-e1f8c6cca02d")
        self.assertEqual(len(set(facts["mapped_source_ids"].values())), 3)
        status, checks, _ = self.run_checks(token=None)
        self.assertEqual(status, "NOT_A_LIVE_HOST")
        self.assertEqual({c["result"] for c in checks if c["name"].startswith(("TOKEN", "NO_ACL"))},
                         {"NOT_APPLICABLE"})

    def test_head_and_tree(self):
        for kw, name in (({"head": "b" * 40}, "HEAD_IS_APPROVED"), ({"expect": ""}, "HEAD_IS_APPROVED"),
                         ({"head": None}, "HEAD_IS_APPROVED"), ({"porcelain": " M gateway/service.py"}, "TREE_CLEAN"),
                         ({"porcelain": None}, "TREE_CLEAN")):
            status, checks, _ = self.run_checks(token=CLEAN_TOKEN, **kw)
            self.assertEqual((status, self.result(checks, name)), ("FAIL", "FAIL"), kw)

    def test_committed_configs_must_stay_disabled(self):
        status, checks, _ = self.run_checks(token=CLEAN_TOKEN, disabled=False)
        self.assertEqual((status, self.result(checks, "COMMITTED_CONFIGS_DISABLED")), ("FAIL", "FAIL"))
        self.assertTrue(pf.committed_configs_disabled())          # the repository as committed

    def edited_config(self, name, cfg_edit=None, index_edit=None) -> Path:
        d = Path(self._tmp.name) / name
        d.mkdir()
        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        index = (self.syn / "INDEX.pilot.stage-b.yaml").read_text(encoding="utf-8")
        if index_edit:
            index = index_edit(index)
        (d / "INDEX.pilot.stage-b.yaml").write_text(index, encoding="utf-8")
        cfg["index_path"] = str(d / "INDEX.pilot.stage-b.yaml")
        if cfg_edit:
            cfg_edit(cfg)
        (d / "gateway.json").write_text(json.dumps(cfg), encoding="utf-8")
        return d / "gateway.json"

    def test_scope_refusals(self):
        cases = {
            "mode_mcp_stdio": self.edited_config("live", cfg_edit=lambda c: c["notebooklm"].update(mode="mcp_stdio")),
            "injection_mapped": self.edited_config("inj", index_edit=lambda s: s.replace(
                "8ccb8115-f552-4ecb-b42a-f0ee093f1d08", "b710e565-91f6-49f1-bea6-a6783cbca9f4")),
            "second_notebook": self.edited_config("nb2", index_edit=lambda s: s.replace(
                'notebooklm_notebooks: ["8ca84143-c240-4fcb-98fe-e1f8c6cca02d"]',
                'notebooklm_notebooks: ["8ca84143-c240-4fcb-98fe-e1f8c6cca02d", "nb-other"]')),
            "missing_config": Path(self._tmp.name) / "absent.json",
        }
        for name, cfg in cases.items():
            status, checks, _ = self.run_checks(token=CLEAN_TOKEN, config=cfg)
            self.assertEqual((status, self.result(checks, "STAGE_B_SCOPE")), ("FAIL", "FAIL"), name)

    def test_server_pin_and_tool_set(self):
        spec = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        variants = {
            "other_pin": lambda s: s["mcpServers"]["gemini-notebook-mcp"].update(
                args=[a.replace("0.15.1", "0.16.0") for a in s["mcpServers"]["gemini-notebook-mcp"]["args"]]),
            "extra_tool": lambda s: s["mcpServers"]["gemini-notebook-mcp"]["env"].update(
                NOTEBOOKLM_ENABLED_TOOLS="notebook_list,notebook_get,source_get_content,notebook_query,source_add"),
            "not_uvx": lambda s: s["mcpServers"]["gemini-notebook-mcp"].update(command="nlm"),
            "no_server": lambda s: s["mcpServers"].pop("gemini-notebook-mcp"),
        }
        for name, edit in variants.items():
            s = json.loads(json.dumps(spec))
            edit(s)
            path = Path(self._tmp.name) / f"mcp-{name}.json"
            path.write_text(json.dumps(s), encoding="utf-8")
            status, checks, _ = self.run_checks(token=CLEAN_TOKEN, mcp_json=path)
            self.assertEqual((status, self.result(checks, "M01_SERVER_PIN")), ("FAIL", "FAIL"), name)

    def test_token_checks(self):
        for token, name in (({**CLEAN_TOKEN, "elevated": True}, "TOKEN_NOT_ELEVATED"),
                            ({**CLEAN_TOKEN, "integrity_rid": 0x3000, "integrity": "High"},
                             "TOKEN_INTEGRITY_AT_MOST_MEDIUM"),
                            ({**CLEAN_TOKEN, "privileges": ["SeBackupPrivilege"]}, "NO_ACL_BYPASS_PRIVILEGES")):
            status, checks, _ = self.run_checks(token=token)
            self.assertEqual((status, self.result(checks, name)), ("FAIL", "FAIL"), name)

    def test_the_preflight_never_reads_the_local_library(self):
        # the stage-B config names a source root; the contract-v2 preflight must not need it to exist
        cfg = self.edited_config("noroot", cfg_edit=lambda c: c.update(source_root=str(Path(self._tmp.name) / "none")))
        status, _checks, _ = self.run_checks(token=CLEAN_TOKEN, config=cfg)
        self.assertEqual(status, "PASS")


if __name__ == "__main__":
    unittest.main()
