# F8 retry-generation assertion (option B) (sandbox Linux, 2026-10-08)

Scope: NEXT_ALLOWED_STEP `M02_PATCH_F8_RETRY_GENERATION_ASSERTION_AND_OWNER_WINDOWS_OFFLINE_RERUN_ONLY`
(GPT_REVIEW_V1 at `378d5f0`, option B).
- Only `tests/m02/test_gateway_regressions.py` changed.
- `gateway/adapters/notebooklm.py`, `gateway/retry.py` and all runtime behaviour are unchanged.

Changes to `F8NoBackendWorkAfterTheBudget`:
- **`test_reviewer_repro_no_query_after_timeout_return`** no longer asserts `c._proc is None`. It still requires:
  - no call after the caller returned (`assertNoCallAfter`), and one or two calls at most;
  - via `assertRetryLeftOnlyAValidatedIdleGeneration`:
    - the generation whose `tools/call` was in flight (the pre-started pid) has exactly one teardown,
      `reason: retire`, `verified: true`;
    - if a process remains, it is a new pid and a higher generation, validated on the exact four-tool surface with
      no escaped process, ready and alive. Its explicit `close()` gives a teardown `reason: close`,
      `verified: true`;
    - if no process remains, `_ready` is false.
- **`test_retry_generation_validated_then_expired_before_send_is_kept_idle_and_closes_verified`** (new) is a
  deterministic seam for that branch:
  - attempt 1's in-flight `tools/call` times out and generation 1 is retired;
  - in a 3 s attempt, a wrapped `_start` validates a new generation, then waits until the attempt deadline has
    passed, so `tools/call` is refused before sending;
  - the test requires that the server log holds only attempt 1's call, that there is no call after return, and
    that a kept generation exists and satisfies the same assertions, close verified included.

Validation:
- The two F8 tests together, 30 consecutive runs: 0 failures.
- `m02-suite-x5.txt`: the M02 suite, 5 consecutive verbose runs, each 158 tests OK, 4 skipped (Windows-only).

Windows acceptance needs the owner to re-run the whole offline suite on ducdq at this exact code commit.
