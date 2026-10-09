# Contract v2 Windows offline acceptance (owner machine ducdq, 2026-10-09): FAILED

- **Scope:** NEXT_ALLOWED_STEP `OWNER_WINDOWS_CONTRACT_V2_OFFLINE_ACCEPTANCE_ONLY`, from the GPT_REVIEW_V1 PASS at
  `eec1680`.
- **Commit:** the owner fast-forwarded the branch and checked that `git rev-parse HEAD` printed
  `eec1680632162f3af869cbe99bc4492df19d2f5e` with a clean tree. The code-tested commit is `fa1ab74`; the HEAD
  commit adds evidence only.
- **Command:** `scripts\m02\m02-tests.ps1 -WithClaude` in PowerShell. Claude Code was 2.1.293. The runner
  stops at the first failing step.
- **Offline only:** fixtures and the local Python stand-ins (`fake_uvx_wrapper.py`, `fake_mcp_server.py`). No
  NotebookLM, no login, and no config, pin, policy or permission change.
- **Console output:** `m02-tests-windows.txt`, as pasted by the owner.

**Result: FAILED.**
- **Unit and contract tests:** 168 tests, 1 failure, 1 error, 3 skipped.
- **Steps not run:** the runner stopped, so the M01 regression, the secret scan and the real Claude Code
  `surface` and `llm` checks did not run.
- **Contract v2 on Windows:** not accepted. No B2 run follows.

## Failures

Both failures are the same Gateway refusal, raised in `McpStdioNotebookLMClient._start`:
`BACKEND_UNAVAILABLE: a NotebookLM MCP server process is outside its containment; refusing to use it`.

| Test | Process chain started by the client |
|---|---|
| `test_gateway_f13_f14.F14ProcessTree.test_graceful_close_also_verifies_the_tree` (ERROR) | `sys.executable fake_uvx_wrapper.py -- sys.executable fake_mcp_server.py` |
| `test_gateway_surface_harness.TemporaryFakeBackend.test_lookup_through_the_generated_command_returns_v2_evidence_from_the_fake` (FAIL) | Gateway (via the stderr wrapper) → `sys.executable fake_mcp_server.py` |

In both cases `initialize` and the exact four-tool `tools/list` had succeeded. The client then found a live
descendant of the server process outside its job object and refused to use the server. The refusal itself is
fail closed, as designed.

The skipped tests are:
- the POSIX-only escape test;
- two symlink tests that need privileges on Windows.

The four Windows-only junction/reparse controls, which Linux skips, ran here. No failure was reported for them in
the output.

## Implementer's analysis (for review; a hypothesis, not yet confirmed on the machine)

1. **Assignment happens after the process starts.** `_ProcessTree` puts the server into a kill-on-close job
   (`_win_job_assign`) right after `subprocess.Popen` returns. Any child the server creates before that
   assignment is outside the job. `escaped()` counts such children, and `_start` then refuses the server.
2. **The interpreter creates a child at once.** Both chains start `sys.executable`. Under `uv run` on Windows,
   that is the virtual environment's `python.exe` launcher, which starts the base interpreter as a child process
   as soon as it runs. The owner's earlier error message in the same paste is consistent with this: it names the
   base interpreter `...\uv\python\cpython-3.11-windows-x86_64-none\python.exe` although `uv run` was used.
   - If the launcher creates that child before the Gateway's `AssignProcessToJobObject` call, the child is
     outside the job.
   - Whether that happens depends on timing, so it is a race.
3. **Unchanged code, so the failure is intermittent.** The containment code is unchanged since `6ed225b`:
   `git diff 6ed225b eec1680 -- gateway/adapters/notebooklm.py` shows only the `Citation.number` lines.
   - At `6ed225b` the same F14 tests passed on this machine, including
     `test_graceful_close_also_verifies_the_tree` and `test_recovery_runs_on_a_new_validated_process`
     (`../windows-ducdq-2026-10-08-f14/`).
   - This points to an intermittent race, not a contract-v2 change.
4. **The real server has the same race.** Its chain is `uvx.exe` → python, so on Windows a live start could
   also be refused intermittently. It would fail closed: the escaped process is never used. The 2026-10-07 B2
   live run predates F14 containment.
5. **Linux and POSIX do not have this window.** `start_new_session` sets the process group before `exec`.
6. **Not yet confirmed.** The output does not show the escaped process count or pids
   (`details.escaped_processes` is not printed).

## Proposed fix (not implemented; F14 runtime is outside the patch scopes reviewed so far)

- **Remove the window in the runtime.** On Windows, start the server suspended (`CREATE_SUSPENDED`), assign the
  job, then resume its thread or threads. No descendant can then exist outside the job.
  - Resuming uses documented Win32 calls: Toolhelp32 thread snapshot, then `OpenThread` with
    `THREAD_SUSPEND_RESUME`, then `ResumeThread`.
  - If the assignment fails, kill the suspended process and keep the existing containment `none` path, which
    gives BLOCKED.
- **Regression tests:**
  - A test-only seam that delays the job assignment after process creation. With today's code it reproduces the
    escape deterministically on Windows: the start is refused. With the fix, the process stays suspended until
    the assignment, so the start is accepted and `escaped_processes` is 0.
  - A loop of repeated starts through the launcher chain, asserting zero escapes every time.
- **Then:** the Linux suite, then a new owner Windows run of the same offline acceptance.

An optional read-only diagnostic could confirm the cause first: repeat the two tests on Windows and print the
`escaped_processes` details. It uses no NotebookLM and changes nothing.

## Note on the earlier part of the paste

The paste first repeats the 2026-10-07 B2 console, recorded in `../windows-ducdq-2026-10-07-b2/`:
- head `67874a3`;
- preflight-before PASS;
- stage-B FAIL at P8;
- preflight-after PASS.

It also shows a second `pilot_stage_b.py --live` run at 2026-10-07T09:30:02Z, right after preflight-after:
- same case results, FAIL at P8;
- summary `stage-b-20261007-093002.summary.json`, not provided and not recorded here.

That historical run was not listed in the B2 README. Nothing live was run in this round.

No credentials, cookies, real document text or raw transcripts are included.
