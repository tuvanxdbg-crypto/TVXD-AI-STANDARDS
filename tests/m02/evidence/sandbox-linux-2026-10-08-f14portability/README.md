# F14 negative-test portability (sandbox Linux, 2026-10-08)

Scope: NEXT_ALLOWED_STEP `M02_PATCH_F14_WINDOWS_NEGATIVE_TEST_PORTABILITY_ONLY` (GPT_REVIEW_V1 at `6b92227`).
- Only `tests/m02/test_gateway_f13_f14.py` changed. Gateway adapter/runtime, runner verdicts, F13/F12, mappings,
  INDEX/source gate, audit seal, configs and pin/policy are unchanged.

Changes:
- `no_containment_init()` simulates containment that could not be set up, as when `_win_job_assign` returns
  `None`.
  - No job or process group is created, and none is closed. Closing a real kill-on-close job kills the stand-in on
    Windows, which is a different failure mode.
  - Used by `test_containment_unavailable_is_blocked_not_pass` and by `patch_nth_tree(3, unavailable=True)`.
- `test_recovery_containment_unavailable_is_blocked` selects the recovery teardown by the patched pid. It
  requires `containment: none`, `tree_empty: null`, `verified: false`, P8 and run `BLOCKED` and exit 3, and the
  timed-out teardown verified.
- `test_recovery_wrapper_exits_but_descendant_survives_is_fail` keeps every verdict and record assertion: run
  FAIL, exit 1, `wrapper_exited: true`, `tree_empty: false`, `verified: false`, measured before the job closes. Only
  the sleeper's state after close is split:
  - POSIX: still alive;
  - Windows: dead, because closing the kill-on-close job is a backstop.

`m02-suite-x3.txt`: the M02 suite, 3 consecutive verbose runs.

Windows acceptance still needs the owner to re-run the whole offline suite on ducdq at the new exact code commit.

## Run 3 of `m02-suite-x3.txt` FAILED: a pre-existing F8 race, made more frequent (finding, not fixed here)

Runs 1 and 2 passed (157 tests, OK, 4 skipped). Run 3 failed one test outside this patch:
`test_gateway_regressions.F8NoBackendWorkAfterTheBudget.test_reviewer_repro_no_query_after_timeout_return`
(`assertIsNone(c._proc)` 1 s after the caller's TIMEOUT).

Diagnosis (`f8_race_diag.py`, `f8_race_diag_portable.py`; offline, fake server only):
- The test uses `timeout_s` 0.05, 2 attempts and `total_budget_s` 0.1. Attempt 1's in-flight `tools/call` times
  out, and its process is retired and verified.
- Attempt 2, the retry, sometimes starts and validates a **new** server (initialize + exact `tools/list`) within
  its own ~50 ms. Its deadline then passes before `tools/call`, so the request is refused before sending
  ("deadline passed before sending").
- By the existing F8 design, a request refused before sending leaves the validated process in place. So 1 s later
  `_proc` is the new, ready, idle process. The server log shows `start`, `call notebook_query`, `start`, with no
  second call. Nothing reached the backend after the budget, and `assertNoCallAfter` passed.
- Frequency, 80 runs of the same scenario:
  - pre-F14 code (`17090da`): 1/80;
  - current code: 9/80.
- With `-k` on the single test, 25 runs: 0/25 at `17090da`, 2/25 now.
- So the race predates F14. F14's teardown changes the timing so that attempt 2 more often gets the client in
  time.

Proposed for review (outside `M02_PATCH_F14_WINDOWS_NEGATIVE_TEST_PORTABILITY_ONLY`, so not done here):
- **(A) runtime:** when a call's attempt expires or is cancelled after it started a server process but before
  sending `tools/call`, terminate and record that process too (`reason: abandoned_start`). After a timed-out call,
  no process it started would then remain. This matches the adapter's stated invariant ("no late work of a
  timed-out attempt remains").
- **(B) test-only:** assert that attempt 1's process was retired, instead of `_proc is None`.

(A) is the stricter option. Either one needs a review decision before the owner's Windows re-run, because the race
can make that run red.
