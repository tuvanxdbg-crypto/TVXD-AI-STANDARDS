"""D6 layer 2 / D7: the report writer refuses anything that could touch an existing file.

Each refusal case checks three things: the exit code is non-zero; the target (or the file it points to) keeps its
sha256 and size; no `.cadaudit-tmp-*` file is left. Run on Linux and Windows; only file-symlink cases are skipped
(with a stated reason) when the OS refuses to create the symlink. Junction (Windows) and hard link cases always run.
"""
import json
import os
import stat
import subprocess
import sys
import unittest
from unittest import mock

import m04_helpers
from cadaudit import _report_writer
from cadaudit.errors import CadAuditError
from m04_helpers import (REPO, World, check_args, make_dir_link, read_bytes, read_json, remove_link, run_cli,
                         sha256_of, tmp_files_under)

KEEP = b'{"keep": "this existing file must not change"}\n'


class WriterCase(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.addCleanup(self.w.cleanup)

    def symlink(self, target, link):
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"cannot create a file symlink on this machine ({type(e).__name__}); needs Developer Mode or admin on Windows")
        self.w.links.append(link)

    def run_check(self, out, input_path=None, rules_path=None):
        return run_cli(*check_args(input_path or self.w.input, rules_path or self.w.rules, out))

    def assert_refused(self, out, protected=(), code=None, expect_out_absent=False):
        """Run the CLI and check the three conditions. `protected` are files whose bytes must not change."""
        before = self.w.snapshot(*protected, self.w.input, self.w.rules)
        listing = self.w.listing()
        exit_code, err = self.run_check(out)
        self.assertNotEqual(exit_code, 0, err)
        self.assertEqual(exit_code, 3, err)
        if code:
            self.assertIn(f"ERROR {code}", err)
        self.assertEqual(self.w.snapshot(*protected, self.w.input, self.w.rules), before)       # sha256 and size
        self.assertEqual(tmp_files_under(self.w.root), [])                                       # no temp file
        self.assertEqual(self.w.listing(), listing)                                              # nothing was created
        if expect_out_absent:
            self.assertFalse(os.path.lexists(out))
        return err


class RefusalCases(WriterCase):
    def test_1_existing_regular_json_file(self):
        out = self.w.out("existing.json")
        with open(out, "wb") as f:
            f.write(KEEP)
        self.assert_refused(out, protected=[out], code="OUT_EXISTS")
        self.assertEqual(read_bytes(out), KEEP)

    def test_2_symlink_to_fake_dwg(self):
        out = self.w.out("link.json")
        self.symlink(self.w.dwg, out)
        self.assert_refused(out, protected=[self.w.dwg], code="OUT_EXISTS")
        self.assertTrue(os.path.islink(out))

    def test_3_dangling_symlink(self):
        missing = os.path.join(self.w.cad, "not-there.dwg")
        out = self.w.out("dangling.json")
        self.symlink(missing, out)
        self.assert_refused(out, code="OUT_EXISTS")
        self.assertFalse(os.path.lexists(missing), "the report must not be created through a dangling link")
        self.assertTrue(os.path.islink(out))

    def test_4_hard_link_to_fake_dwg(self):
        out = self.w.out("hard.json")
        os.link(self.w.dwg, out)
        self.assertEqual(os.lstat(self.w.dwg).st_nlink, 2)
        self.assert_refused(out, protected=[self.w.dwg, out], code="OUT_EXISTS")
        self.assertEqual(os.lstat(self.w.dwg).st_nlink, 2)
        self.assertEqual(read_bytes(self.w.dwg), m04_helpers.FAKE_DWG_BYTES)

    def test_5_parent_is_a_symlink_or_junction(self):
        real = os.path.join(self.w.root, "real-out")
        os.mkdir(real)
        link = os.path.join(self.w.root, "link-out")
        make_dir_link(self, link, real)
        self.w.links.append(link)
        out = os.path.join(link, "report.json")
        self.assert_refused(out, code="OUT_PARENT_")
        self.assertEqual(os.listdir(real), [])

    def test_5b_link_further_up_the_path(self):
        real = os.path.join(self.w.root, "real-root")
        os.makedirs(os.path.join(real, "sub"))
        link = os.path.join(self.w.root, "link-root")
        make_dir_link(self, link, real)
        self.w.links.append(link)
        self.assert_refused(os.path.join(link, "sub", "report.json"), code="OUT_PARENT_NOT_CANONICAL")
        self.assertEqual(os.listdir(os.path.join(real, "sub")), [])

    def test_5c_error_message_tells_the_user_to_pass_the_full_path(self):
        real = os.path.join(self.w.root, "real-out")
        os.mkdir(real)
        link = os.path.join(self.w.root, "link-out")
        make_dir_link(self, link, real)
        self.w.links.append(link)
        err = self.assert_refused(os.path.join(link, "sub", "report.json"))   # parent does not exist behind the link
        self.assertTrue("OUT_PARENT" in err)
        real_sub = os.path.join(real, "sub")
        os.mkdir(real_sub)
        err = self.run_check(os.path.join(link, "sub", "report.json"))[1]
        self.assertIn("full long path", err)
        self.assertIn("8.3", err)

    def test_6_suffix_not_json(self):
        for name in ("report.txt", "report.dwg", "report", "report.json.dwg", ".json", "report.json.", "report.jsonl", "report.JSON.bak"):
            with self.subTest(name):
                self.assert_refused(self.w.out(name), code="OUT_SUFFIX_NOT_JSON", expect_out_absent=True)

    def test_7_out_is_the_input(self):
        self.assert_refused(self.w.input, protected=[self.w.input], code="OUT_IS_INPUT")

    def test_7b_out_is_the_rules_file(self):
        before = sha256_of(self.w.rules)
        code, err = run_cli(*check_args(self.w.input, self.w.rules, self.w.rules))
        self.assertEqual(code, 3)
        self.assertIn("OUT_", err)
        self.assertEqual(sha256_of(self.w.rules), before)

    def test_7c_out_is_the_input_through_a_different_spelling(self):
        spelled = os.path.join(self.w.indir, "..", "in", "cad_read.json")
        self.assert_refused(spelled, protected=[self.w.input], code="OUT_IS_INPUT")

    def test_8_out_inside_the_input_directory(self):
        sub = os.path.join(self.w.indir, "sub")
        os.mkdir(sub)
        self.assert_refused(os.path.join(self.w.indir, "report.json"), code="OUT_IN_INPUT_DIR", expect_out_absent=True)
        self.assert_refused(os.path.join(sub, "report.json"), code="OUT_IN_INPUT_DIR", expect_out_absent=True)

    def test_8b_out_inside_the_rules_directory(self):
        self.assert_refused(os.path.join(self.w.rulesdir, "report.json"), code="OUT_IN_INPUT_DIR", expect_out_absent=True)

    def test_9_failure_in_the_middle_of_writing(self):
        out = self.w.out("report.json")
        neighbour = self.w.out("neighbour.json")
        with open(neighbour, "wb") as f:
            f.write(KEEP)
        real_write = os.write

        def half_then_fail(fd, data):
            real_write(fd, bytes(data[:7]))        # a partial temp file really exists on disk
            raise OSError(28, "No space left on device (simulated)")

        with mock.patch.object(_report_writer, "_write_all", side_effect=lambda fd, data: half_then_fail(fd, data)):
            before = self.w.snapshot(neighbour, self.w.input, self.w.rules)
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("OUT_WRITE_FAILED", err)
        self.assertFalse(os.path.lexists(out))
        self.assertEqual(tmp_files_under(self.w.root), [])
        self.assertEqual(self.w.snapshot(neighbour, self.w.input, self.w.rules), before)
        self.assertEqual(sorted(os.listdir(self.w.outdir)), ["neighbour.json"])

    def test_9b_failure_while_publishing(self):
        out = self.w.out("report.json")
        target = "rename" if os.name == "nt" else "link"
        with mock.patch.object(os, target, side_effect=OSError(1, "simulated publish failure")):
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertFalse(os.path.lexists(out))
        self.assertEqual(tmp_files_under(self.w.root), [])

    def test_9c_target_appears_during_publish_is_not_replaced(self):
        out = self.w.out("report.json")
        target = "rename" if os.name == "nt" else "link"

        def appears_then_exists(*args, **kwargs):
            with open(out, "wb") as f:                # somebody creates the file between check and publish
                f.write(KEEP)
            raise FileExistsError(17, "File exists")

        with mock.patch.object(os, target, side_effect=appears_then_exists):
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("OUT_EXISTS", err)
        self.assertEqual(read_bytes(out), KEEP)
        self.assertEqual(tmp_files_under(self.w.root), [])

    def test_out_is_a_directory(self):
        out = self.w.out("dir.json")
        os.mkdir(out)
        self.assert_refused(out, code="OUT_EXISTS")

    def test_parent_missing_or_not_a_directory(self):
        self.assert_refused(os.path.join(self.w.root, "nope", "report.json"), code="OUT_PARENT_MISSING")
        not_dir = os.path.join(self.w.root, "file-not-dir")
        with open(not_dir, "wb") as f:
            f.write(KEEP)
        self.assert_refused(os.path.join(not_dir, "report.json"), protected=[not_dir])

    def test_temp_name_prefix_is_not_a_valid_target(self):
        self.assert_refused(self.w.out(".cadaudit-tmp-abc.json"), code="OUT_INVALID", expect_out_absent=True)

    @unittest.skipUnless(os.name == "nt", "Windows file-name rules")
    def test_windows_reserved_names_and_streams(self):
        for name in ("CON.json", "nul.json", "report.json:stream.json", "a<b.json"):
            with self.subTest(name):
                self.assert_refused(self.w.out(name), code="OUT_")

    def test_verify_step_deletes_nothing_when_the_file_is_not_the_expected_one(self):
        path = self.w.out("v.json")
        with open(path, "wb") as f:
            f.write(b"abc")
        dfd = os.open(self.w.outdir, os.O_RDONLY) if os.name != "nt" else None
        try:
            with self.assertRaises(CadAuditError) as cm:
                _report_writer._verify(os.name != "nt", dfd, self.w.outdir, "v.json", "0" * 64, 3)   # wrong hash
            self.assertEqual(cm.exception.code, "OUT_VERIFY_FAILED")
            with self.assertRaises(CadAuditError):
                _report_writer._verify(os.name != "nt", dfd, self.w.outdir, "v.json", "0" * 64, 4)   # wrong size
            alias = self.w.out("v-alias.json")
            os.link(path, alias)                                                                      # st_nlink == 2
            with self.assertRaises(CadAuditError) as cm:
                import hashlib
                _report_writer._verify(os.name != "nt", dfd, self.w.outdir, "v.json", hashlib.sha256(b"abc").hexdigest(), 3)
            self.assertEqual(cm.exception.code, "OUT_VERIFY_FAILED")
        finally:
            if dfd is not None:
                os.close(dfd)
        self.assertEqual(read_bytes(path), b"abc")
        self.assertEqual(read_bytes(alias), b"abc")


class ParentIdentityAndSteps(WriterCase):
    """Review L1 (the parent's identity is the one check_target saw) and L4 (messages name the step reached)."""

    @unittest.skipIf(os.name == "nt", "Windows has no dir_fd: the parent identity comparison is POSIX only (documented limit)")
    def test_L1_parent_replaced_right_after_check_target(self):
        out = self.w.out("report.json")
        old_dir = self.w.outdir + "_old"
        real = _report_writer.check_target

        def racing(out_path, input_path, rules_path):
            result = real(out_path, input_path, rules_path)
            os.rename(self.w.outdir, old_dir)       # the checked parent moves away ...
            os.mkdir(self.w.outdir)                 # ... and a new directory now sits at the same path
            return result

        before = self.w.snapshot(self.w.input, self.w.rules)
        with mock.patch.object(_report_writer, "check_target", racing):     # cli keeps its own reference: only write_report races
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("OUT_PARENT_CHANGED", err)
        self.assertEqual(os.listdir(self.w.outdir), [])        # nothing was created in the new directory
        self.assertEqual(os.listdir(old_dir), [])              # nor in the old one
        self.assertEqual(tmp_files_under(self.w.root), [])
        self.assertEqual(self.w.snapshot(self.w.input, self.w.rules), before)

    def test_L1_check_target_returns_the_parent_identity(self):
        parent, name, parent_id = _report_writer.check_target(self.w.out("r.json"), self.w.input, self.w.rules)
        st = os.lstat(self.w.outdir)
        self.assertEqual((parent, name, parent_id), (self.w.outdir, "r.json", (st.st_dev, st.st_ino)))

    def test_L4_verify_failure_after_publish_says_the_report_exists(self):
        out = self.w.out("report.json")
        with mock.patch.object(_report_writer, "_verify", side_effect=OSError(5, "simulated read failure")):
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("OUT_WRITE_FAILED", err)
        self.assertIn("the report exists under its final name", err)
        self.assertIn("nothing was deleted", err)
        self.assertNotIn("no report was written", err)
        self.assertTrue(os.path.isfile(out))                    # it really is there, and was not deleted
        self.assertEqual(json.loads(read_bytes(out).decode("utf-8"))["schema"], "tvxd.cadaudit.report/v1")
        self.assertEqual(tmp_files_under(self.w.root), [])

    def test_L4_real_verify_mismatch_says_the_report_exists_and_nothing_was_deleted(self):
        out = self.w.out("report.json")
        with mock.patch.object(os, "read", return_value=b""):   # the read-back differs from what was built
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("OUT_VERIFY_FAILED", err)
        self.assertIn("the report exists under --out", err)
        self.assertIn("nothing was deleted", err)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(tmp_files_under(self.w.root), [])

    def test_L4_failure_before_publish_says_no_report_was_written(self):
        out = self.w.out("report.json")
        target = "rename" if os.name == "nt" else "link"
        with mock.patch.object(os, target, side_effect=OSError(1, "simulated publish failure")):
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("no report was written", err)
        self.assertFalse(os.path.lexists(out))
        self.assertEqual(tmp_files_under(self.w.root), [])

    @unittest.skipIf(os.name == "nt", "the link-then-unlink publish step exists on POSIX only")
    def test_L4_after_link_the_message_names_the_temporary_name(self):
        out = self.w.out("report.json")
        with mock.patch.object(os, "unlink", side_effect=OSError(1, "simulated unlink failure")):
            code, err = self.run_check(out)
        self.assertEqual(code, 3, err)
        self.assertIn("the report exists under its final name; its temporary name could not be removed", err)
        self.assertNotIn("no report was written", err)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(len(tmp_files_under(self.w.root)), 1)  # unlink is patched to fail, so the cleanup attempt fails too and the temporary name stays
        self.assertEqual(read_bytes(out), read_bytes(tmp_files_under(self.w.root)[0]))


class PositiveCases(WriterCase):
    def test_fresh_out_path_succeeds_and_is_a_single_regular_file(self):
        out = self.w.out("report.json")
        code, err = self.run_check(out)
        self.assertEqual(code, 0, err)
        st = os.lstat(out)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(st.st_nlink, 1)
        rep = read_json(out)
        self.assertEqual(rep["schema"], "tvxd.cadaudit.report/v1")
        self.assertEqual(rep["summary"]["overall"], "ALL_RULES_PASS")
        self.assertEqual(os.listdir(self.w.outdir), ["report.json"])
        self.assertEqual(tmp_files_under(self.w.root), [])

    def test_second_run_to_the_same_path_is_refused_and_keeps_the_first_report(self):
        out = self.w.out("report.json")
        self.assertEqual(self.run_check(out)[0], 0)
        first = read_bytes(out)
        code, err = self.run_check(out)
        self.assertEqual(code, 3)
        self.assertIn("OUT_EXISTS", err)
        self.assertEqual(read_bytes(out), first)

    def test_dot_dot_in_the_path_is_normalised(self):
        out = os.path.join(self.w.outdir, "..", "out", "report.json")
        self.assertEqual(self.run_check(out)[0], 0)
        self.assertTrue(os.path.exists(self.w.out("report.json")))

    def test_input_files_are_unchanged_by_a_successful_run(self):
        before = self.w.snapshot(self.w.input, self.w.rules)
        self.assertEqual(self.run_check(self.w.out("r.json"))[0], 0)
        self.assertEqual(self.w.snapshot(self.w.input, self.w.rules), before)

    def test_report_is_written_exactly_as_built(self):
        out = self.w.out("report.json")
        data = b'{"x": 1}\n'
        _report_writer.write_report(out, data, self.w.input, self.w.rules)
        self.assertEqual(read_bytes(out), data)


class EndToEnd(WriterCase):
    def run_module(self, *args):
        return subprocess.run([sys.executable, "-m", "cadaudit", *args], cwd=REPO, capture_output=True, timeout=120)

    def test_python_dash_m_cadaudit_check(self):
        out = self.w.out("report.json")
        r = self.run_module(*check_args(self.w.input, self.w.rules, out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read_json(out)["summary"]["overall"], "ALL_RULES_PASS")
        r = self.run_module(*check_args(self.w.input, self.w.rules, out))
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"OUT_EXISTS", r.stderr)

    def test_python_dash_m_cadaudit_input_error_leaves_nothing(self):
        out = self.w.out("report.json")
        r = self.run_module(*check_args(os.path.join(m04_helpers.FIX, "error_read_mode_read_write.json"), self.w.rules, out))
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"READ_MODE_NOT_READ_ONLY", r.stderr)
        self.assertEqual(os.listdir(self.w.outdir), [])


if __name__ == "__main__":
    unittest.main()
