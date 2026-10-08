# F14 Windows process-tree offline verification (owner machine ducdq, 2026-10-08)

Scope: NEXT_ALLOWED_STEP `OWNER_WINDOWS_F14_PROCESS_TREE_OFFLINE_VERIFICATION_AT_6ED225_ONLY` (GPT_REVIEW_V1 PASS
at `6ed225b`).
- The owner ran the M02 offline suite in PowerShell on ducdq at exact code
  `6ed225b2a7f5b58e52bae1927982412a42fd804e`, checked with `git rev-parse HEAD` first.
- Runtime: `uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z`.
- No NotebookLM, no login, no `mcp_stdio` against the real server. The tests start only local Python stand-ins:
  `fake_uvx_wrapper.py` → `fake_mcp_server.py`, plus a sleeper in one test.
- `m02-suite-windows.txt` is the console output the owner pasted into the chat.

**Result: FAILED (157 tests, 2 failures, 1 error, 3 skipped).** F14 on Windows is therefore **not yet accepted**.
No B2 run.

## Passed on Windows, the job-object path exercised

| Test | What it shows on Windows |
|---|---|
| `F14ProcessTree.test_retirement_kills_and_verifies_wrapper_and_child` | retire: job terminated, wrapper exited, job empty (`verified`), wrapper and child pids gone |
| `F14ProcessTree.test_graceful_close_also_verifies_the_tree` | close: teardown `verified`, no stand-in pid alive |
| `F14ProcessTree.test_negative_control_wrapper_only_kill_leaves_the_child_and_p8_fails` | without the job kill, the child keeps the job non-empty: `tree_empty: false`, P8 FAIL |
| `F14ProcessTree.test_recovery_runs_on_a_new_validated_process` | recovery on a new pid with 4 tools and no escaped process |
| `F14RunnerEndToEnd.test_all_cases_pass_with_startup_timeout_and_verified_teardown` | whole runner: all six cases PASS; timed-out and recovery teardowns both verified with containment; no pid alive |
| `F14RunnerEndToEnd.test_call_timeout_variant_counts_the_query_as_sent` | call-timeout variant PASS; `sent_to_backend` true |
| `F14TimeoutDetails` (3 tests) | startup timeout `initialize`/`false`; call timeout `tools/call`/`true` |
| `F13*` (11 tests) and the rest of the suite | as on Linux |

Skipped:
- the POSIX-only escape test;
- two symlink tests that need privileges on Windows. These were skipped before as well.

## Failed on Windows: implementer's analysis, for review

All three are negative tests that simulate a defect by patching `_ProcessTree`. On Windows, the patch itself
changes what happens.

1. **`F14ProcessTree.test_containment_unavailable_is_blocked_not_pass`: `BACKEND_UNAVAILABLE` instead of
   `TIMEOUT`.**
   - The test simulates "containment unavailable" by building the real tree and then calling `tree.close()`.
   - On Windows that closes the kill-on-close job handle, which kills the wrapper and child at once. The call
     then fails with "server exited" before the timeout.
   - Gateway behaviour is fail-closed (no query sent), but the simulated scenario is not the intended one.
2. **`F14RunnerEndToEnd.test_recovery_containment_unavailable_is_blocked`: `ValueError` at the unpack of
   `recover_teardowns`.**
   - The asserts before it held: run status `BLOCKED`, exit 3, stopped after P8.
   - Same cause as 1: the patched recovery process was killed when its job closed. The client retried on a new,
     contained process, so `recover_teardowns` has two entries:
     - the patched one, `containment: none`;
     - the retried one, verified.
   - The verdict was `BLOCKED`, as intended, but the test expected exactly one entry.
3. **`F14RunnerEndToEnd.test_recovery_wrapper_exits_but_descendant_survives_is_fail`: the recovery sleeper is
   not alive at the end of the test.**
   - The asserts before it held: run `FAIL`, exit 1, stopped after P8. The recovery teardown had
     `wrapper_exited: true`, `tree_empty: false`, `verified: false`, measured before the job handle was closed.
   - After that measurement, `_record_teardown` closes the job handle, and kill-on-close then kills the
     surviving sleeper. That is a Windows backstop, not a gap.
   - The test's final `pid_alive` assertion is a POSIX assumption.

Proposed fix (test-only, not implemented; for review):
- (1) and (2): simulate unavailable containment without creating or closing a job, i.e. a `_ProcessTree` with
  `kind = "none"` and no job handle, the same as a failed `_win_job_assign`. For (2), assert on the entry whose
  pid is the patched one.
- (3): assert `pid_alive` of the recovery sleeper only on POSIX. On Windows, assert it is dead after the job
  close (backstop).

Then the owner re-runs the same offline suite on ducdq. No Gateway or runner code change is proposed.
