#!/usr/bin/env python3
"""M02 Windows-only confinement controls (OWNER_WINDOWS_M02_FIXTURE_ACCEPTANCE), on the local source adapter.

Contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE) no longer reads local files in standards_lookup, so these
negative controls now exercise gateway.adapters.local.LocalSourceAdapter directly (it stays in the repository for
the historical stage-A tooling); they were not removed.

A junction (directory reparse point) or a file symlink inside the source root that points outside it
must be refused, and the outside canary must never be read or returned. A normal path stays readable.
Everything is built in a throwaway copy of tests/m02/fixtures; the real library is never touched.
Skipped on non-Windows. Junctions need no privilege (`mklink /J`); file symlinks need Developer Mode
or SeCreateSymbolicLinkPrivilege, so that sub-check is skipped when creation is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest

from helpers import FixtureCopy

from gateway.adapters.local import LocalSourceAdapter
from gateway.config import load_config
from gateway.errors import GatewayError
from gateway.index import load_index

OUTSIDE_CANARY = "TVXD-M02-OUTSIDE-ROOT-CANARY-7A3C"
QCVN_2024 = "02_QCVN/QCVN-FAKE-01-2024.md"


@unittest.skipUnless(sys.platform == "win32", "Windows junction/reparse controls")
class WindowsReparseConfinement(unittest.TestCase):
    def setUp(self):
        self.fx = FixtureCopy()
        self.outside_dir = self.fx.root / "outside-root"
        self.outside_dir.mkdir()
        self.outside_file = self.outside_dir / "secret.md"
        self.outside_file.write_text(f"# Ngoài root\n\n2 Phần ngoài\n\n2.1 {OUTSIDE_CANARY}\n", encoding="utf-8")
        self.links: list = []

    def tearDown(self):
        for link in self.links:   # remove the reparse points first, never their targets
            try:
                os.rmdir(link) if link.is_dir() else os.unlink(link)
            except OSError:
                pass
        self.fx.cleanup()

    def junction(self, link, target) -> None:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode != 0 or not link.exists():
            self.skipTest("mklink /J is not available on this machine")
        self.links.append(link)

    def point_index_at(self, rel: str) -> None:
        """Make QCVN-FAKE-01@2024 point at `rel`, with the outside file's real hash (so only confinement can refuse)."""
        sha = hashlib.sha256(self.outside_file.read_bytes()).hexdigest()
        text = self.fx.index.read_text(encoding="utf-8")
        old_sha = hashlib.sha256((self.fx.library / QCVN_2024).read_bytes()).hexdigest()
        text = text.replace(f'path: "{QCVN_2024}"', f'path: "{rel}"', 1).replace(old_sha, sha)
        self.fx.index.write_text(text, encoding="utf-8")

    def adapter(self) -> LocalSourceAdapter:
        cfg = load_config(self.fx.config)
        return LocalSourceAdapter(cfg.source_root, cfg.limits)

    def qcvn_2024(self):
        return load_index(self.fx.index).documents["QCVN-FAKE-01"].versions[0]

    def assertRefusedWithoutReading(self, rel: str) -> None:
        local = self.adapter()
        reads = local.reads
        with self.assertRaises(GatewayError) as cm:
            local.resolve(rel)
        self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED", rel)
        self.point_index_at(rel)
        with self.assertRaises(GatewayError) as cm:
            local.load(self.qcvn_2024())
        self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED", rel)
        self.assertNotIn(OUTSIDE_CANARY, json.dumps(cm.exception.to_dict(), ensure_ascii=False))
        self.assertEqual(local.reads, reads, "the outside file must not be read")

    def test_normal_path_control_is_readable(self):
        doc = self.adapter().load(self.qcvn_2024())
        self.assertIn("1111 mm", "\n".join(doc.text.lines))

    def test_directory_junction_inside_root_to_outside_is_refused(self):
        link = self.fx.library / "02_QCVN" / "jdir"
        self.junction(link, self.outside_dir)
        self.assertTrue((link / "secret.md").exists())          # the junction really points outside
        self.assertRefusedWithoutReading("02_QCVN/jdir/secret.md")

    def test_junction_as_top_level_folder_is_refused(self):
        link = self.fx.library / "06_JUNCTION"
        self.junction(link, self.outside_dir)
        self.assertRefusedWithoutReading("06_JUNCTION/secret.md")

    def test_file_symlink_inside_root_to_outside_is_refused(self):
        link = self.fx.library / "02_QCVN" / "link.md"
        try:
            os.symlink(self.outside_file, link)
        except OSError:
            self.skipTest("file symlinks need Developer Mode or SeCreateSymbolicLinkPrivilege")
        self.links.append(link)
        self.assertRefusedWithoutReading("02_QCVN/link.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
