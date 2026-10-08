#!/usr/bin/env python3
"""Regressions for GPT_REVIEW_V1 at 17090da (B2 live findings). Fixtures, fakes and local stand-in processes only.

F13: strict normalization of the notebooklm-mcp-cli 0.15.1 citation shape (citations {number: source_id},
references [{source_id, citation_number, cited_text}], sources_used) and of the earlier object shape. In-scope,
consistent responses become FOUND; any missing, malformed, contradictory or out-of-scope entry discards the whole
response (CITED_SOURCE_NOT_WHITELISTED, no answer, evidence, cache or VERIFIED).

F14: timeout details name the MCP method / phase and whether notebook_query's tools/call was written; P8 judges
only a terminal attempt; teardown kills and verifies the whole server process tree (a uvx-like wrapper and its
child); recovery runs on a new process that passed initialize + the exact tools/list check.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HERE, lookup, make_service

import pilot_stage_b as sb
import test_gateway_regressions as reg
from fake_notebooklm import FakeNotebookLM
from gateway import schema
from gateway.adapters import notebooklm as nlm
from gateway.adapters.notebooklm import McpStdioNotebookLMClient, NotebookLMAdapter, check_citations
from gateway.errors import GatewayError

A, B, C = "src-a", "src-b", "src-c"
QCVN, PASSAGE, ELEC = reg.QCVN_SRC, reg.QCVN_PASSAGE, reg.ELEC
INJECTED = "TVXD-M02-F13-DISCARDED-ANSWER-4C7A"


def shape_015(cites, *, answer=INJECTED, sources_used=None, references=None):
    """notebooklm-mcp-cli 0.15.1 result body: cites = [(source_id, cited_text)], numbered from 1."""
    return {"answer": answer, "question": "q", "conversation_id": "c",
            "citations": {str(n): sid for n, (sid, _) in enumerate(cites, start=1)},
            "references": references if references is not None else
            [{"source_id": sid, "citation_number": n, "cited_text": text} for n, (sid, text) in enumerate(cites, 1)],
            "sources_used": sources_used if sources_used is not None else list(dict.fromkeys(s for s, _ in cites))}


class F13CheckCitations(unittest.TestCase):
    """check_citations against the queried ids [A, B, C]."""

    def discard(self, body):
        return check_citations(body, [A, B, C]).discard

    def test_exact_015_shape_in_scope_is_usable_with_passages_by_number(self):
        chk = check_citations(shape_015([(A, "pa"), (B, "pb"), (A, "pa2")]), [A, B, C])
        self.assertEqual((chk.discard, chk.problems, chk.out_of_scope), ([], [], []))
        self.assertEqual([(c.source_id, c.passage) for c in chk.citations], [(A, "pa"), (B, "pb"), (A, "pa2")])
        self.assertEqual(chk.shape["citation_value_kinds"], ["string"])
        self.assertEqual(chk.shape["reference_item_keys"], ["citation_number", "cited_text", "source_id"])

    def test_int_keys_and_missing_cited_text_are_accepted(self):
        body = {"citations": {1: A}, "references": [{"source_id": A, "citation_number": 1}], "sources_used": [A]}
        chk = check_citations(body, [A, B, C])
        self.assertEqual((chk.discard, [(c.source_id, c.passage) for c in chk.citations]), ([], [(A, None)]))

    def test_earlier_object_shape_still_accepted(self):
        chk = check_citations({"citations": [{"source_id": A, "passage": "p"}]}, [A, B, C])
        self.assertEqual((chk.discard, [(c.source_id, c.passage) for c in chk.citations]), ([], [(A, "p")]))
        chk = check_citations({"citations": {"1": {"source_id": B, "cited_text": "q"}}}, [A, B, C])
        self.assertEqual((chk.discard, [(c.source_id, c.passage) for c in chk.citations]), ([], [(B, "q")]))

    def test_out_of_scope_in_any_container_is_reported_by_id(self):
        self.assertEqual(self.discard(shape_015([(A, "x"), ("src-x", "y")])), ["src-x"])
        body = shape_015([(A, "x")])
        body["references"].append({"source_id": "src-y", "cited_text": "z"})
        self.assertEqual(self.discard(body), ["src-y"])
        self.assertEqual(self.discard(shape_015([(A, "x")], sources_used=[A, "src-z"])), ["src-z"])

    def test_missing_or_malformed_ids_are_unattributed(self):
        for value in (None, "", 5, ["src-a"], " src-a", True):
            body = shape_015([(A, "x")])
            body["citations"]["2"] = value
            self.assertEqual(self.discard(body), ["<unattributed>"], repr(value))
        body = shape_015([(A, "x")])
        body["references"].append({"citation_number": 1, "cited_text": "no id"})
        self.assertEqual(self.discard(body), ["<unattributed>"])
        self.assertEqual(self.discard(shape_015([(A, "x")], sources_used=[A, None])), ["<unattributed>"])
        self.assertEqual(self.discard({"citations": {"1": A}, "references": ["src-a"], "sources_used": [A]}),
                         ["<unattributed>"])

    def test_sources_used_never_rescues_a_malformed_citation(self):
        body = {"citations": {"1": None}, "references": [], "sources_used": [A]}
        self.assertIn("<unattributed>", self.discard(body))
        body = {"citations": {"1": {"passage": "no id"}}, "sources_used": [A]}
        self.assertIn("<unattributed>", self.discard(body))

    def test_contradictions_between_containers_are_inconsistent(self):
        cases = {
            "reference number names another source": shape_015(
                [(A, "x"), (B, "y")], references=[{"source_id": B, "citation_number": 1, "cited_text": "x"}]),
            "reference number without citation": shape_015(
                [(A, "x")], references=[{"source_id": A, "citation_number": 2, "cited_text": "x"}]),
            "cited id missing from sources_used": shape_015([(A, "x"), (B, "y")], sources_used=[A]),
            "in-scope sources_used id nothing cites": shape_015([(A, "x")], sources_used=[A, B]),
            "unnumbered reference to an uncited source": shape_015(
                [(A, "x")], references=[{"source_id": B, "cited_text": "y"}], sources_used=[A, B]),
            "two references, one number, two sources": shape_015(
                [(A, "x")], references=[{"source_id": A, "citation_number": 1},
                                        {"source_id": B, "citation_number": 1}], sources_used=[A, B]),
        }
        for name, body in cases.items():
            self.assertEqual(self.discard(body), ["<inconsistent>"], name)

    def test_malformed_numbers_text_and_containers_are_inconsistent(self):
        for key in ("one", "0", "-1", "01", "1.0"):
            self.assertEqual(self.discard({"citations": {key: A}, "sources_used": [A]}), ["<inconsistent>"], key)
        self.assertEqual(self.discard({"citations": {True: A}, "sources_used": [A]}), ["<inconsistent>"])
        self.assertEqual(self.discard({"citations": {"1": A, 1: A}, "sources_used": [A]}), ["<inconsistent>"])
        for ref in ({"source_id": A, "citation_number": "x"}, {"source_id": A, "citation_number": 1, "cited_text": 7}):
            self.assertEqual(self.discard({"citations": {"1": A}, "references": [ref], "sources_used": [A]}),
                             ["<inconsistent>"], ref)
        for body in ({"citations": "src-a"}, {"citations": {"1": A}, "references": {"source_id": A}},
                     {"citations": {"1": A}, "sources_used": "src-a"}):
            self.assertEqual(self.discard(body), ["<inconsistent>"], body)

    def test_live_b2_shape_is_no_longer_a_p10_trigger(self):
        """The five B2 responses: citations a dict of string ids, sources_used the mapped TCVN 8794 source only."""
        ids = sorted(sb.fake_answer("clean")["sources_used"] + ["8b75af2d-4477-40fb-a67f-3ee10173c221",
                                                                 "d54bb084-5c50-4cef-8979-6e909f791c1e"])
        body = {"status": "success", "answer": "x", "question": "q", "conversation_id": "c",
                "citations": {str(n): sb.TCVN_8794_SOURCE for n in range(1, 8)},
                "references": [{"source_id": sb.TCVN_8794_SOURCE, "citation_number": n, "cited_text": "t"}
                               for n in range(1, 8)],
                "sources_used": [sb.TCVN_8794_SOURCE]}
        chk = check_citations(body, ids)
        self.assertEqual((chk.discard, chk.problems, len(chk.citations)), ([], [], 7))


class F13ServiceDiscard(reg.Base):
    """Through the Gateway: in-scope 0.15.1 shape is FOUND (verify, cache); every bad variant is discarded whole."""

    def run_lookup(self, body):
        fake = FakeNotebookLM({"nb-fixture-001": body})
        svc, logs = make_service(self.fx.config, client=fake)
        r = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)
        self.assertFalse(schema.check(r, "lookup.response.v1.json"))
        return fake, svc, logs, r

    def test_exact_015_shape_in_scope_found_verified_and_cached(self):
        fake, svc, _logs, r = self.run_lookup(shape_015([(QCVN, PASSAGE)], answer="(fake) trả lời"))
        self.assertEqual(r["status"], "FOUND")
        ev = r["results"][0]
        self.assertEqual((ev["STATUS"], ev["RETRIEVAL_PATH"]["route"]), ("VERIFIED", "NOTEBOOKLM"))
        self.assertEqual(self.verify(svc, ev)["status"], "VERIFIED")
        again = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)
        self.assertEqual((len(fake.calls), again["results"][0]["RETRIEVAL_PATH"]["cache_hit"]), (1, True))

    def test_bad_variants_discard_answer_evidence_and_cache(self):
        variants = {
            "out-of-scope citation value": (shape_015([(QCVN, PASSAGE), ("src-m01-injection", "x")]),
                                            ["src-m01-injection"]),
            "out-of-scope reference only": (shape_015([(QCVN, PASSAGE)], references=[
                {"source_id": QCVN, "citation_number": 1, "cited_text": PASSAGE},
                {"source_id": "src-m01-injection", "cited_text": "x"}]), ["src-m01-injection"]),
            "non-string citation value": ({"answer": INJECTED, "citations": {"1": 7}, "sources_used": [QCVN]},
                                          ["<unattributed>"]),
            "reference without source id": (shape_015([(QCVN, PASSAGE)], references=[
                {"citation_number": 1, "cited_text": PASSAGE}]), ["<unattributed>"]),
            "reference number conflict": (shape_015([(QCVN, PASSAGE)], references=[
                {"source_id": QCVN, "citation_number": 2, "cited_text": PASSAGE}]), ["<inconsistent>"]),
            "malformed citation number": ({"answer": INJECTED, "citations": {"x": QCVN}, "sources_used": [QCVN]},
                                          ["<inconsistent>"]),
        }
        for name, (body, expected) in variants.items():
            with self.subTest(name):
                fake, svc, logs, r = self.run_lookup(body)
                self.assertEqual((r["status"], r["error"]["code"], r["results"]),
                                 ("ERROR", "CITED_SOURCE_NOT_WHITELISTED", []))
                self.assertEqual(r["error"]["details"]["out_of_scope_source_ids"], expected)
                dump = json.dumps(r, ensure_ascii=False) + logs.getvalue()
                self.assertNotIn(INJECTED, dump)
                self.assertNotIn(PASSAGE, dump)
                self.assertEqual(len(svc.registry), 0)
                again = lookup(svc, query="khoảng cách trước tủ điện", **ELEC)
                self.assertEqual((len(fake.calls), again["error"]["code"]), (2, "CITED_SOURCE_NOT_WHITELISTED"))


# ---------------------------------------------------------------------------- F14

def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k = ctypes.WinDLL("kernel32")
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        k.CloseHandle(ctypes.c_void_p(h))
        return code.value == 259   # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def kill_pid(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def no_containment_init(tree, proc) -> None:
    """_ProcessTree.__init__ as when containment cannot be set up (e.g. _win_job_assign returned None): no job is
    created, so none is closed. Closing a real kill-on-close job would kill the stand-in itself on Windows, which
    is a different failure mode (GPT_REVIEW_V1 at 6b92227)."""
    tree.proc, tree.kind, tree._job = proc, "none", None


class StandIn(unittest.TestCase):
    """McpStdioNotebookLMClient against fake_uvx_wrapper.py -> fake_mcp_server.py (a two-process tree)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m02-f14-")
        self.dir = Path(self.tmp.name)
        self.log, self.child_pids = self.dir / "server.log", self.dir / "child.pids"
        self.answer = self.dir / "answer.json"
        self.answer.write_text(json.dumps(sb.fake_answer("clean"), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        for pid in self.pids() + self.sleepers():
            kill_pid(pid)
        self.tmp.cleanup()

    def pids(self) -> list[int]:
        return [int(x) for x in self.child_pids.read_text().split()] if self.child_pids.exists() else []

    def sleepers(self) -> list[int]:
        f = self.dir / "sleeper.pids"
        return [int(x) for x in f.read_text().split()] if f.exists() else []

    def config(self, *server_options: str, wrapper_options=(), name="mcp.json") -> Path:
        cfg = self.dir / name
        cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {
            "command": sys.executable,
            "args": [str(HERE / "fake_uvx_wrapper.py"), "--pid-file", str(self.child_pids), *wrapper_options, "--",
                     sys.executable, str(HERE / "fake_mcp_server.py"), "--log", str(self.log),
                     "--answer-file", str(self.answer), *server_options]}}}), encoding="utf-8")
        return cfg

    def client(self, *server_options: str, **kw) -> McpStdioNotebookLMClient:
        c = McpStdioNotebookLMClient(self.config(*server_options, **kw), start_timeout_s=10)
        self.addCleanup(c.close)
        return c

    def log_lines(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def tight_query(self, client) -> tuple[sb.Audit, dict]:
        """One notebook_query through Recorder with a 1 s budget; waits until the attempt is terminal."""
        audit = sb.Audit(sorted([A, B, C]))
        adapter = NotebookLMAdapter(sb.Recorder(client, audit, "p8"), timeout_s=1, max_attempts=1, total_budget_s=1)
        with self.assertRaises(GatewayError) as cm:
            adapter.query(sb.NOTEBOOK, "q", [A, B, C])
        self.assertEqual(cm.exception.code, "TIMEOUT")
        self.assertTrue(audit.wait_terminal([1], 15))
        return audit, audit.entries[0]


class F14TimeoutDetails(StandIn):
    def test_startup_timeout_is_not_counted_as_a_sent_notebook_query(self):
        c = self.client("--init-delay", "2.5")
        _audit, e = self.tight_query(c)
        self.assertEqual((e["outcome"], e["exception"], e["failed_method"], e["failed_phase"], e["sent_to_backend"]),
                         ("exception", "TIMEOUT", "initialize", "startup", False))
        self.assertNotIn("call notebook_query", self.log_lines())

    def test_call_timeout_after_the_request_was_written_is_counted_as_sent(self):
        c = self.client("--call-delay", "3")
        _audit, e = self.tight_query(c)
        self.assertEqual((e["failed_method"], e["failed_phase"], e["sent_to_backend"]), ("tools/call", "call", True))
        self.assertIn("call notebook_query", self.log_lines())

    def test_sent_state_mapping(self):
        f = sb.sent_state
        self.assertIs(f({"method": "tools/call", "sent": True}), True)
        self.assertIs(f({"method": "tools/call", "sent": False, "phase": "queue"}), False)
        self.assertEqual(f({"method": "tools/call", "sent": "not_confirmed"}), "not_confirmed")
        self.assertIs(f({"method": "initialize", "sent": True, "phase": "startup"}), False)
        self.assertIs(f({"method": "tools/list", "sent": True}), False)
        self.assertEqual(f({}), "not_confirmed")
        self.assertEqual(f({"request_id": 3}), "not_confirmed")    # an id alone no longer proves the query was sent


class F14ProcessTree(StandIn):
    def test_retirement_kills_and_verifies_wrapper_and_child(self):
        c = self.client("--call-delay", "3")
        self.tight_query(c)
        st = c.process_state()
        (spawned,), (teardown,) = st["spawned"], st["teardowns"]
        self.assertEqual((st["alive"], teardown["pid"], teardown["reason"]), (False, spawned["pid"], "retire"))
        self.assertEqual((teardown["wrapper_exited"], teardown["tree_empty"], teardown["verified"]), (True, True, True))
        (child,) = self.pids()
        self.assertFalse(pid_alive(child))
        self.assertFalse(pid_alive(spawned["pid"]))

    def test_recovery_runs_on_a_new_validated_process(self):
        c = self.client("--call-delay", "3", "--call-delay-once", str(self.dir / "once"))
        self.tight_query(c)
        res = NotebookLMAdapter(c, timeout_s=10, max_attempts=1, total_budget_s=10).query(
            sb.NOTEBOOK, "q", sorted(sb.fake_answer("clean")["sources_used"]))
        self.assertEqual(res.out_of_scope_source_ids, [])
        st = c.process_state()
        self.assertEqual(len(st["validated_starts"]), 2)
        first, second = st["validated_starts"]
        self.assertNotEqual(first["pid"], second["pid"])
        self.assertEqual((second["tools"], second["escaped_processes"] in (0, None)), (4, True))

    def test_graceful_close_also_verifies_the_tree(self):
        c = self.client()
        NotebookLMAdapter(c, timeout_s=10, max_attempts=1, total_budget_s=10).query(
            sb.NOTEBOOK, "q", sorted(sb.fake_answer("clean")["sources_used"]))
        c.close()
        (teardown,) = c.process_state()["teardowns"]
        self.assertEqual((teardown["reason"], teardown["verified"]), ("close", True))
        self.assertFalse(any(pid_alive(p) for p in self.pids()))

    def test_negative_control_wrapper_only_kill_leaves_the_child_and_p8_fails(self):
        orig = nlm._ProcessTree.kill
        nlm._ProcessTree.kill = lambda self: None          # the pre-F14 behaviour: kill only the wrapper
        try:
            c = self.client("--call-delay", "3")
            before = c.process_state()
            audit, e = self.tight_query(c)
            result, obs = sb.p8_judge_teardown(audit, [e], c.process_state, before)
        finally:
            nlm._ProcessTree.kill = orig
        (teardown,) = obs["teardowns"]
        self.assertEqual((teardown["wrapper_exited"], teardown["tree_empty"], teardown["verified"]),
                         (True, False, False))
        # tree_empty False: the child was still alive after the 5 s verification window, exactly what F14 must
        # catch (it exits later, only because closing its stdin ends the stand-in's read loop)
        self.assertEqual(result, "FAIL")

    def test_containment_unavailable_is_blocked_not_pass(self):
        orig = nlm._ProcessTree.__init__
        nlm._ProcessTree.__init__ = no_containment_init
        try:
            c = self.client("--call-delay", "3")
            before = c.process_state()
            audit, e = self.tight_query(c)
            result, obs = sb.p8_judge_teardown(audit, [e], c.process_state, before)
        finally:
            nlm._ProcessTree.__init__ = orig
        (teardown,) = obs["teardowns"]
        self.assertEqual((teardown["containment"], teardown["tree_empty"], teardown["verified"]), ("none", None, False))
        self.assertEqual(result, "BLOCKED")

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX session escape check reads /proc")
    def test_a_descendant_outside_the_containment_refuses_the_start(self):
        c = self.client(wrapper_options=("--child-new-session",))
        with self.assertRaises(GatewayError) as cm:
            c.notebook_list()
        self.assertEqual((cm.exception.code, cm.exception.details.get("escaped_processes")), ("BACKEND_UNAVAILABLE", 1))
        self.assertEqual((c.process_state()["validated_starts"], c.process_state()["alive"]), ([], False))


class F14RunnerEndToEnd(StandIn):
    """The whole B2 runner offline against the real MCP client and the two-process stand-in."""

    @classmethod
    def setUpClass(cls):
        cls._syn = tempfile.TemporaryDirectory(prefix="m02-f14-syn-")
        subprocess.run([sys.executable, str(HERE / "make_pilot_synthetic.py"), str(Path(cls._syn.name) / "syn")],
                       check=True, capture_output=True)
        cls.syn_config = Path(cls._syn.name) / "syn" / "gateway.pilot.stage-b.json"

    @classmethod
    def tearDownClass(cls):
        cls._syn.cleanup()

    def patch_nth_tree(self, n: int, change=None, *, unavailable: bool = False) -> list[int]:
        """For the n-th _ProcessTree built from now on (1-based): build it without containment (`unavailable`), or
        apply `change(tree)` after the real build. Returns the pids it hit.
        Run order: main client (1), P8 timed-out attempt (2), P8 recovery (3)."""
        orig, count, hit = nlm._ProcessTree.__init__, [0], []

        def patched(tree, proc):
            count[0] += 1
            if count[0] == n and unavailable:
                no_containment_init(tree, proc)
            else:
                orig(tree, proc)
            if count[0] == n:
                if change:
                    change(tree)
                hit.append(proc.pid)
        nlm._ProcessTree.__init__ = patched
        self.addCleanup(setattr, nlm._ProcessTree, "__init__", orig)
        return hit

    def run_runner(self, slow_options):
        main_cfg = self.config(name="main.json")
        slow_cfg = self.config(*slow_options, name="slow.json")
        made = []

        def make_client(slow=False):
            c = McpStdioNotebookLMClient(slow_cfg if slow else main_cfg, start_timeout_s=10)
            made.append(c)
            return c
        code, s = sb.execute(self.syn_config, make_client, kind="stand-in", out=self.dir / "out")
        return code, s, made

    def test_all_cases_pass_with_startup_timeout_and_verified_teardown(self):
        code, s, made = self.run_runner(("--init-delay", "2.5", "--delay-once", str(self.dir / "once")))
        self.assertEqual((code, s["status"]), (0, "PASS"), json.dumps(s["cases"], ensure_ascii=False)[:3000])
        self.assertEqual({c["id"]: c["result"] for c in s["cases"]},
                         {"P5": "PASS", "P10": "PASS", "P6": "PASS", "P7": "PASS", "P11": "PASS", "P8": "PASS"})
        p10 = next(c for c in s["cases"] if c["id"] == "P10")
        self.assertEqual(p10["observed"]["outcome"], "OUT_OF_SCOPE_NOT_OBSERVED")
        p8 = next(c for c in s["cases"] if c["id"] == "P8")["observed"]
        self.assertEqual((p8["tight_terminal"], p8["tight_failed_method"], p8["tight_sent_to_backend"]),
                         (True, ["initialize"], [False]))
        (spawned,), (teardown,) = p8["spawned"], p8["teardowns"]
        self.assertEqual((teardown["pid"], teardown["verified"]), (spawned["pid"], True))
        (fresh,) = p8["recover_validated_starts"]
        self.assertNotEqual(fresh["pid"], spawned["pid"])
        # both teardowns are in the P8 summary, and both verified (GPT_REVIEW_V1 at 8762641)
        (rec_spawned,), (rec_teardown,) = p8["recover_spawned"], p8["recover_teardowns"]
        self.assertEqual((rec_spawned["pid"], rec_teardown["pid"], rec_teardown["reason"]),
                         (fresh["pid"], fresh["pid"], "close"))
        self.assertEqual((rec_teardown["wrapper_exited"], rec_teardown["containment"] != "none",
                          rec_teardown["tree_empty"], rec_teardown["verified"]), (True, True, True, True))
        self.assertFalse(p8["process_alive_after_close"])
        self.assertEqual(s["sent_to_backend_count"], s["attempt_count"] - 1)   # the startup timeout sent nothing
        self.assertFalse(any(pid_alive(p) for p in self.pids()))
        text = Path(s["summary_file"]).read_text(encoding="utf-8")
        for leak in ("câu trả lời giả lập", sb.FAKE_PASSAGE):
            self.assertNotIn(leak, text)

    def test_recovery_containment_unavailable_is_blocked(self):
        hit = self.patch_nth_tree(3, unavailable=True)
        code, s, _ = self.run_runner(("--init-delay", "2.5", "--delay-once", str(self.dir / "once")))
        self.assertEqual((code, s["status"], s["stopped_after"]), (3, "BLOCKED", "P8"))
        p8 = next(c for c in s["cases"] if c["id"] == "P8")
        self.assertEqual(p8["result"], "BLOCKED")
        (tight,) = p8["observed"]["teardowns"]
        self.assertTrue(tight["verified"])                       # the timed-out teardown was fine; recovery is not
        # select the recovery teardown by the patched pid (a valid client retry may add entries)
        rec = [x for x in p8["observed"]["recover_teardowns"] if x["pid"] == hit[0]]
        self.assertEqual(len(rec), 1)
        self.assertEqual((rec[0]["containment"], rec[0]["tree_empty"], rec[0]["verified"]), ("none", None, False))

    def test_recovery_wrapper_exits_but_descendant_survives_is_fail(self):
        nlm._ProcessTree.VERIFY_S = 1.0
        self.addCleanup(setattr, nlm._ProcessTree, "VERIFY_S", 5.0)
        hit = self.patch_nth_tree(3, lambda tree: setattr(tree, "kill", lambda: None))   # wrapper-only teardown
        code, s, _ = self.run_runner(("--init-delay", "2.5", "--delay-once", str(self.dir / "once"),
                                      "--spawn-sleeper", str(self.dir / "sleeper.pids")))
        self.assertEqual((code, s["status"], s["stopped_after"]), (1, "FAIL", "P8"))
        p8 = next(c for c in s["cases"] if c["id"] == "P8")
        (tight,), (rec,) = p8["observed"]["teardowns"], p8["observed"]["recover_teardowns"]
        self.assertEqual((tight["verified"], rec["pid"], rec["wrapper_exited"], rec["tree_empty"], rec["verified"]),
                         (True, hit[0], True, False, False))
        # the verdict rests on the record above (measured before the job handle closes). After it: POSIX leaves
        # the recovery server's descendant alive; on Windows closing the kill-on-close job is a backstop that ends it
        if os.name == "nt":
            self.assertFalse(pid_alive(self.sleepers()[-1]))
        else:
            self.assertTrue(pid_alive(self.sleepers()[-1]))
        self.assertFalse(pid_alive(self.sleepers()[0]))          # the timed-out server's one was killed with its tree

    def test_call_timeout_variant_counts_the_query_as_sent(self):
        code, s, _ = self.run_runner(("--call-delay", "3", "--call-delay-once", str(self.dir / "once")))
        self.assertEqual((code, s["status"]), (0, "PASS"))
        p8 = next(c for c in s["cases"] if c["id"] == "P8")["observed"]
        self.assertEqual((p8["tight_failed_method"], p8["tight_sent_to_backend"]), (["tools/call"], [True]))
        self.assertEqual(s["sent_to_backend_count"], s["attempt_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
