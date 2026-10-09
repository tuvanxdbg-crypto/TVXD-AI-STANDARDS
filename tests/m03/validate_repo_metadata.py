#!/usr/bin/env python3
"""M03 D5: machine checks for the safety conditions already settled in M01/M02 (docs/M03_GITHUB_GOVERNANCE.md §4 D5).

Offline. Reads only files tracked by Git in the target repository (`git ls-files`); no network, no NotebookLM, no
local document library, no login state. Uses the standard library, PyYAML and the existing `gateway/` code.

Checks (each PASS / FAIL):
  GATEWAY_CONFIGS_VALID_AND_DISABLED  every tracked JSON file with schema tvxd.gateway.config/v1 is valid against
                                      config.v1.json and has notebooklm.mode exactly "disabled"; at least one exists
  INDEX_FILES_VALID                   every tracked INDEX*.yaml loads with gateway.index.load_index(); a file whose
                                      name contains ".template." must fail to load (templates fail closed)
  M01_SERVER_PIN                      .mcp.json starts gemini-notebook-mcp as uvx --from notebooklm-mcp-cli==0.15.1
                                      with exactly the four M01 read tools (server_pin_problems())
  M01_POLICY_CONSISTENT               allowed tools in config/m01-tool-policy.yaml (allowed_tools and
                                      server_gating.NOTEBOOKLM_ENABLED_TOOLS) and in .claude/settings.json
                                      (permissions.allow) are exactly the four M01 read tools
  GATEWAY_NOT_IN_PROJECT_MCP          .mcp.json has no tvxd-standards-gateway server and no server running
                                      gateway.server (CLAUDE.md)
  SCHEMAS_PARSE                       every gateway/schemas/*.json is valid JSON with "$id" or "title"

Exit 0 when every check is PASS, 1 otherwise.

  uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \\
      python tests/m03/validate_repo_metadata.py [--repo PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "m02"))

from gateway import schema  # noqa: E402
from gateway.adapters.notebooklm import M01_READ_TOOLS  # noqa: E402
from gateway.errors import GatewayError  # noqa: E402
from gateway.index import load_index  # noqa: E402
from pilot_stage_b_v2_preflight import SERVER, server_pin_problems  # noqa: E402

CONFIG_SCHEMA = "tvxd.gateway.config/v1"
GATEWAY_SERVER = "tvxd-standards-gateway"
CHECKS = ("GATEWAY_CONFIGS_VALID_AND_DISABLED", "INDEX_FILES_VALID", "M01_SERVER_PIN", "M01_POLICY_CONSISTENT",
          "GATEWAY_NOT_IN_PROJECT_MCP", "SCHEMAS_PARSE")


def tracked(repo: Path, *patterns: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", *patterns], cwd=repo, capture_output=True, text=True,
                         timeout=60, check=True).stdout
    return sorted(f for f in out.split("\0") if f)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_gateway_configs(repo: Path) -> list[str]:
    problems, seen = [], 0
    for rel in tracked(repo, "*.json"):
        try:
            data = read_json(repo / rel)
        except (OSError, ValueError):
            continue  # not a Gateway config; SCHEMAS_PARSE covers the schema files
        if not (isinstance(data, dict) and data.get("schema") == CONFIG_SCHEMA):
            continue
        seen += 1
        errs = schema.check(data, "config.v1.json")
        if errs:
            problems.append(f"{rel}: not valid against config.v1.json ({errs[0]})")
        mode = (data.get("notebooklm") or {}).get("mode") if isinstance(data.get("notebooklm"), dict) else None
        if mode != "disabled":
            problems.append(f"{rel}: notebooklm.mode is {mode!r}, not 'disabled'")
    if not seen:
        problems.append(f"no tracked {CONFIG_SCHEMA} file found")
    return problems


def check_index_files(repo: Path) -> list[str]:
    problems = []
    files = tracked(repo, "*INDEX*.yaml")
    if not files:
        problems.append("no tracked INDEX*.yaml file found")
    for rel in files:
        template = ".template." in Path(rel).name
        try:
            load_index(repo / rel)
            loaded, why = True, ""
        except GatewayError as e:
            loaded, why = False, f"{e.code}: {e}"
        except Exception as e:  # noqa: BLE001 - any other loader crash is also a failed load
            loaded, why = False, f"load_index raised {type(e).__name__}"
        if template and loaded:
            problems.append(f"{rel}: template loaded, but a template must fail closed")
        elif not template and not loaded:
            problems.append(f"{rel}: {why}")
    return problems


def check_server_pin(repo: Path) -> list[str]:
    return server_pin_problems(repo / ".mcp.json")


def check_policy_consistent(repo: Path) -> list[str]:
    want = sorted(M01_READ_TOOLS)
    problems = []
    try:
        policy = yaml.safe_load((repo / "config" / "m01-tool-policy.yaml").read_text(encoding="utf-8"))
        allowed = sorted(policy["allowed_tools"])
        gated = sorted(policy["server_gating"]["NOTEBOOKLM_ENABLED_TOOLS"])
    except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
        return [f"config/m01-tool-policy.yaml unreadable: {type(e).__name__}"]
    if allowed != want:
        problems.append(f"config/m01-tool-policy.yaml allowed_tools {allowed} != {want}")
    if gated != want:
        problems.append(f"config/m01-tool-policy.yaml server_gating.NOTEBOOKLM_ENABLED_TOOLS {gated} != {want}")
    try:
        allow = read_json(repo / ".claude" / "settings.json")["permissions"]["allow"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return problems + [f".claude/settings.json unreadable: {type(e).__name__}"]
    prefix = f"mcp__{SERVER}__"
    notebook_allow = sorted(a[len(prefix):] for a in allow if isinstance(a, str) and a.startswith(prefix))
    if notebook_allow != want:
        problems.append(f".claude/settings.json permissions.allow NotebookLM tools {notebook_allow} != {want}")
    return problems


def check_gateway_not_in_project_mcp(repo: Path) -> list[str]:
    try:
        servers = read_json(repo / ".mcp.json")["mcpServers"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f".mcp.json unreadable: {type(e).__name__}"]
    problems = []
    if GATEWAY_SERVER in servers:
        problems.append(f".mcp.json has server {GATEWAY_SERVER}")
    for name, spec in servers.items():
        args = [str(a) for a in ((spec or {}).get("args") or [])]
        if "gateway.server" in args:
            problems.append(f".mcp.json server {name} runs gateway.server")
    return problems


def check_schemas_parse(repo: Path) -> list[str]:
    problems = []
    files = sorted((repo / "gateway" / "schemas").glob("*.json"))
    if not files:
        problems.append("no gateway/schemas/*.json file found")
    for path in files:
        rel = path.relative_to(repo).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            problems.append(f"{rel}: not valid JSON ({type(e).__name__})")
            continue
        if not (isinstance(data, dict) and (data.get("$id") or data.get("title"))):
            problems.append(f"{rel}: no $id or title")
    return problems


FUNCS = {
    "GATEWAY_CONFIGS_VALID_AND_DISABLED": check_gateway_configs,
    "INDEX_FILES_VALID": check_index_files,
    "M01_SERVER_PIN": check_server_pin,
    "M01_POLICY_CONSISTENT": check_policy_consistent,
    "GATEWAY_NOT_IN_PROJECT_MCP": check_gateway_not_in_project_mcp,
    "SCHEMAS_PARSE": check_schemas_parse,
}


def run_checks(repo: Path) -> list[dict]:
    results = []
    for name in CHECKS:
        try:
            problems = FUNCS[name](repo)
        except (OSError, subprocess.SubprocessError) as e:
            problems = [f"cannot run: {type(e).__name__}"]
        results.append({"name": name, "result": "FAIL" if problems else "PASS", "problems": problems})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=REPO, help="repository root to check (default: this checkout)")
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    args = ap.parse_args(argv)
    results = run_checks(args.repo.resolve())
    status = "PASS" if all(r["result"] == "PASS" for r in results) else "FAIL"
    if args.json:
        print(json.dumps({"status": status, "checks": results}, indent=2))
    else:
        for r in results:
            print(f"{r['result']:<6} {r['name']}")
            for p in r["problems"]:
                print(f"         - {p}")
        print(f"M03 REPO METADATA: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
