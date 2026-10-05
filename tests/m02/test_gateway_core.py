#!/usr/bin/env python3
"""M02 core units: schemas, INDEX validation, clause parsing, local adapter safety and formats."""
from __future__ import annotations

import os
import sys
import unittest
import zipfile
from pathlib import Path

from helpers import FIXTURES, FixtureCopy, REPO  # noqa: F401  (sets sys.path)

from gateway import schema
from gateway.adapters.local import LocalSourceAdapter, find_clause
from gateway.clauses import canonical_clause, parse_sections
from gateway.config import Limits
from gateway.errors import GatewayError
from gateway.extract import extract
from gateway.index import load_index
from gateway.paths import relpath_problems


class Schemas(unittest.TestCase):
    def test_all_schema_files_load_and_use_supported_keywords(self):
        for p in sorted((REPO / "gateway" / "schemas").glob("*.json")):
            schema.load(p.name)

    def test_lookup_request_negatives(self):
        self.assertTrue(schema.check({}, "lookup.request.v1.json"))                       # missing query
        self.assertTrue(schema.check({"query": "x", "extra": 1}, "lookup.request.v1.json"))
        self.assertTrue(schema.check({"query": "x", "assessment_date": "05/10/2026"}, "lookup.request.v1.json"))
        self.assertTrue(schema.check({"query": "x", "work_code": "bad code!"}, "lookup.request.v1.json"))
        self.assertFalse(schema.check({"query": "x", "work_code": "ELEC-LV-FAKE", "assessment_date": "2026-10-05",
                                       "project_context": {"conditions": {"COND-INDOOR": True}}},
                                      "lookup.request.v1.json"))

    def test_verify_request_needs_evidence_or_id(self):
        self.assertTrue(schema.check({"work_code": "X"}, "verify.request.v1.json"))
        self.assertFalse(schema.check({"evidence_id": "ev_" + "a" * 24}, "verify.request.v1.json"))


class IndexValidation(unittest.TestCase):
    def setUp(self):
        self.fx = FixtureCopy()

    def tearDown(self):
        self.fx.cleanup()

    def assertIndexInvalid(self, old, new):
        self.fx.edit_index(old, new)
        with self.assertRaises(GatewayError) as cm:
            load_index(self.fx.index)
        self.assertEqual(cm.exception.code, "INDEX_INVALID")
        return cm.exception

    def test_fixture_index_is_valid_and_marked_fixture(self):
        idx = load_index(FIXTURES / "INDEX.yaml")
        self.assertTrue(idx.fixture)
        self.assertEqual(len(idx.documents), 9)

    def test_traversal_path_in_index_rejected(self):
        e = self.assertIndexInvalid('path: "02_QCVN/QCVN-FAKE-01-2024.md"', 'path: "../outside/secret.md"')
        self.assertIn("segment '..' not allowed", " ".join(e.details["problems"]))

    def test_absolute_and_backslash_paths_rejected(self):
        for bad in ('"C:/Windows/win.ini"', '"/etc/passwd"', '"02_QCVN\\\\QCVN-FAKE-01-2024.md"'):
            fx = FixtureCopy()
            try:
                fx.edit_index('"02_QCVN/QCVN-FAKE-01-2024.md"', bad)
                with self.assertRaises(GatewayError):
                    load_index(fx.index)
            finally:
                fx.cleanup()

    def test_bad_hash_duplicate_id_unknown_field(self):
        self.assertIndexInvalid('sha256: "', 'sha256: "XYZ')
        fx = FixtureCopy()
        try:
            fx.edit_index("id: QCVN-FAKE-02", "id: QCVN-FAKE-01")
            with self.assertRaises(GatewayError):
                load_index(fx.index)
        finally:
            fx.cleanup()
        self.fx.edit_index("fixture: true", "fixture: true\nunexpected_key: 1")
        with self.assertRaises(GatewayError):
            load_index(self.fx.index)

    def test_whitelist_names_unknown_document(self):
        self.fx.edit_index("HD-FAKE-UNREVIEWED]", "HD-FAKE-UNREVIEWED, NOT-IN-INDEX]")
        with self.assertRaises(GatewayError) as cm:
            load_index(self.fx.index)
        self.assertIn("unknown document NOT-IN-INDEX", " ".join(cm.exception.details["problems"]))


class Paths(unittest.TestCase):
    def test_relpath_rules(self):
        self.assertEqual(relpath_problems("02_QCVN/QCVN-FAKE-01-2024.md"), [])
        self.assertEqual(relpath_problems("03_TCVN/TCVN FAKE 7777 Hệ thống chiếu sáng.md"), [])
        for bad in ["../x.md", "a/../b.md", "/abs.md", "C:/x.md", "a\\b.md", "CON.md", "a/NUL.txt", "x.md:ads",
                    "a//b.md", "trailing./x.md", "a/./b.md", "\\\\server\\share\\x.md",
                    "03_TCVN/TCVN FAKE 7777 He\u0302\u0323 tho\u0302\u0301ng.md"]:  # last one is NFD
            self.assertTrue(relpath_problems(bad), bad)


class Clauses(unittest.TestCase):
    def test_numeric_and_article_parsing(self):
        lines = ("# T", "1 Phạm vi", "1. list item, not a heading", "2 Yêu cầu", "2.1 A", "x", "2.1.1. B", "2.2 C")
        ids = [s.id for s in parse_sections(lines, "numeric")]
        self.assertEqual(ids, ["1", "2", "2.1", "2.1.1", "2.2"])
        art = ("Chương I", "Điều 2. Giải thích", "1. Một", "2. Hai", "a) điểm a", "Điều 3. Khác")
        ids = [s.id for s in parse_sections(art, "article")]
        self.assertEqual(ids, ["Chương I", "Điều 2", "Điều 2 khoản 1", "Điều 2 khoản 2", "Điều 2 khoản 2 điểm a",
                               "Điều 3"])

    def test_canonical_references(self):
        self.assertEqual(canonical_clause("khoản 2 Điều 5", "article"), "Điều 5 khoản 2")
        self.assertEqual(canonical_clause("dieu 5 khoan 2 diem b", "article"), "Điều 5 khoản 2 điểm b")
        self.assertIsNone(canonical_clause("Điều 5 và Điều 6 xyz", "article"))
        self.assertEqual(canonical_clause("mục 2.1", "numeric"), "2.1")
        self.assertIsNone(canonical_clause("2.1; DROP", "numeric"))
        self.assertEqual(canonical_clause("QCVN FAKE 01:2024 mục 2.1 về khoảng cách", "numeric", strict=False), "2.1")
        self.assertIsNone(canonical_clause("QCVN FAKE 01:2024 khoảng cách", "numeric", strict=False))


class LocalAdapter(unittest.TestCase):
    def setUp(self):
        self.fx = FixtureCopy()
        self.idx = load_index(self.fx.index)
        self.local = LocalSourceAdapter(self.fx.library, Limits())

    def tearDown(self):
        self.fx.cleanup()

    def v(self, doc, ver):
        return next(x for x in self.idx.documents[doc].versions if x.version == ver)

    def test_unicode_windows_filename(self):
        doc = self.local.load(self.v("TCVN-FAKE-7777", "2023"))
        self.assertIsNotNone(find_clause(doc, "2.1"))

    def test_docx_extraction_with_table_and_image(self):
        doc = self.local.load(self.v("TCVN-FAKE-8888", "2022"))
        sec = find_clause(doc, "2.2")
        body = doc.text.lines[sec.start:sec.end]
        self.assertIn("| 8,8 | 88 A |", body)
        self.assertIn("[IMAGE]", body)
        self.assertTrue(any(i in doc.text.layout_lines for i in range(sec.start, sec.end)))

    def test_pdf_unsupported_is_structured(self):
        with self.assertRaises(GatewayError) as cm:
            self.local.load(self.v("IEC-FAKE-60000", "2020"))
        self.assertEqual(cm.exception.code, "UNSUPPORTED_FORMAT")

    def test_bad_docx_and_dtd_refused(self):
        with self.assertRaises(GatewayError) as cm:
            extract(b"not a zip", "docx", max_docx_uncompressed=10 ** 6)
        self.assertEqual(cm.exception.code, "EXTRACTION_FAILED")
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
        with self.assertRaises(GatewayError) as cm:
            extract(buf.getvalue(), "docx", max_docx_uncompressed=10 ** 6)
        self.assertIn("DTD", cm.exception.message)

    def test_invalid_utf8_text(self):
        with self.assertRaises(GatewayError) as cm:
            extract(b"\xff\xfe\x00bad", "md", max_docx_uncompressed=1)
        self.assertEqual(cm.exception.code, "EXTRACTION_FAILED")

    def test_traversal_rejected_by_adapter(self):
        for bad in ["../INDEX.yaml", "02_QCVN/../../INDEX.yaml", "/etc/passwd", "C:/x"]:
            with self.assertRaises(GatewayError) as cm:
                self.local.resolve(bad)
            self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED", bad)

    @unittest.skipIf(sys.platform == "win32", "symlink creation needs privileges on Windows")
    def test_symlink_file_and_dir_inside_root_rejected(self):
        outside = self.fx.root / "outside.md"
        outside.write_text("1 Ngoài root\nnội dung ngoài\n", encoding="utf-8")
        os.symlink(outside, self.fx.library / "02_QCVN" / "link.md")
        os.symlink(self.fx.root, self.fx.library / "linkdir")
        for rel in ("02_QCVN/link.md", "linkdir/outside.md"):
            with self.assertRaises(GatewayError) as cm:
                self.local.resolve(rel)
            self.assertEqual(cm.exception.code, "SOURCE_NOT_ALLOWED", rel)

    def test_missing_file_and_size_limit(self):
        with self.assertRaises(GatewayError) as cm:
            self.local.resolve("02_QCVN/missing.md")
        self.assertEqual(cm.exception.code, "SOURCE_NOT_FOUND")
        small = LocalSourceAdapter(self.fx.library, Limits(max_source_bytes=1024))
        with self.assertRaises(GatewayError) as cm:
            small.load(self.v("TCVN-FAKE-8888", "2022"))
        self.assertEqual(cm.exception.code, "EXTRACTION_FAILED")

    def test_hash_mismatch_is_drift(self):
        p = self.fx.library / "02_QCVN" / "QCVN-FAKE-01-2024.md"
        p.write_text(p.read_text(encoding="utf-8").replace("1111", "9999"), encoding="utf-8")
        with self.assertRaises(GatewayError) as cm:
            self.local.load(self.v("QCVN-FAKE-01", "2024"))
        self.assertEqual(cm.exception.code, "SOURCE_DRIFT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
