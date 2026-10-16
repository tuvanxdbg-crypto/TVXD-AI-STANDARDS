"""Shared helpers for the M04-A tests. Fixture data only; nothing here touches a real drawing or the network."""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIX = os.path.join(HERE, "fixtures")
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cadaudit import cli  # noqa: E402

GROUP_ARRAYS = ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs")
FAKE_DWG_BYTES = b"FAKE DWG BYTES CREATED AT TEST RUNTIME - NOT A DRAWING\x00\x01\x02" * 8


def fx(name: str) -> str:
    return os.path.join(FIX, name)


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_json(path: str):
    return json.loads(read_bytes(path).decode("utf-8"))


def sha256_of(path: str) -> str:
    return hashlib.sha256(read_bytes(path)).hexdigest()


def run_cli(*args):
    """Run cadaudit.cli.main in-process. Returns (exit_code, stderr_text)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = cli.main([str(a) for a in args])
    return code, err.getvalue()


def check_args(inp, rules, out):
    return ("check", "--input", inp, "--rules", rules, "--out", out)


def tmp_files_under(root: str) -> list:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):  # followlinks=False: links are not entered
        for name in dirnames + filenames:
            if name.startswith(".cadaudit-tmp-"):
                found.append(os.path.join(dirpath, name))
    return found


def make_dir_link(testcase: unittest.TestCase, link: str, target: str) -> None:
    """Symlink (POSIX) or junction (Windows, mklink /J, no privilege needed) from link to target directory."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
        if r.returncode != 0 or not os.path.exists(link):
            testcase.skipTest("mklink /J is not available on this machine")
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        try:
            os.rmdir(path)  # a junction: removes the junction only, never its target
        except OSError:
            pass


class World:
    """Temp tree: in/ (input), rules/ (rules), cad/ (a fake .dwg made at runtime), out/ (empty output dir)."""

    def __init__(self, input_name="cad_read_pass.json", rules_name="rules_internal.yaml"):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="m04-"))   # realpath: no 8.3 short names
        self.indir = os.path.join(self.root, "in")
        self.rulesdir = os.path.join(self.root, "rules")
        self.cad = os.path.join(self.root, "cad")
        self.outdir = os.path.join(self.root, "out")
        for d in (self.indir, self.rulesdir, self.cad, self.outdir):
            os.mkdir(d)
        self.input = os.path.join(self.indir, "cad_read.json")
        self.rules = os.path.join(self.rulesdir, "rules.yaml")
        shutil.copyfile(fx(input_name), self.input)
        shutil.copyfile(fx(rules_name), self.rules)
        self.dwg = os.path.join(self.cad, "fake-drawing.dwg")
        with open(self.dwg, "wb") as f:
            f.write(FAKE_DWG_BYTES)
        self.links: list = []

    def out(self, name="report.json") -> str:
        return os.path.join(self.outdir, name)

    def cleanup(self) -> None:
        for link in self.links:
            remove_link(link)
        shutil.rmtree(self.root, ignore_errors=True)

    def snapshot(self, *paths) -> dict:
        return {p: (sha256_of(p), os.path.getsize(p)) for p in paths}

    def listing(self) -> list:
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            for name in dirnames + filenames:
                out.append(os.path.relpath(os.path.join(dirpath, name), self.root))
        return sorted(out)


# ---- independent evidence resolver (does not use cadaudit code)
_EV = re.compile(r"CADEV:([A-Za-z0-9_-]+):([0-9A-F]+|FILE):([A-Za-z0-9_.]+)")


def resolve_evidence(doc: dict, ev_id: str) -> list:
    """Return the list of values the evidence ID points to in the input document (must have exactly one)."""
    m = _EV.fullmatch(ev_id)
    if not m:
        return []
    file_id, handle, field = m.groups()
    if file_id != doc["drawing"]["file_id"]:
        return []
    if handle == "FILE":
        parts = field.split(".")
        node = doc["units"][0] if parts[0] == "units" and doc.get("units") else doc
        parts = parts[1:] if parts[0] == "units" else parts
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                return []
            node = node[p]
        return [node]
    return [obj[field] for g in GROUP_ARRAYS for obj in doc.get(g, []) if obj["handle"] == handle and field in obj]
