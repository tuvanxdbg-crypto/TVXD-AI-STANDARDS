set -u
S=<scratch>
W=$S/wt-981f; E=$S/ev3
G="uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z"
cd $W
echo "worktree HEAD $(git rev-parse HEAD)" > $E/env.txt
{ uv --version; $G python --version; $G python -c 'import yaml;print("PyYAML",yaml.__version__)'; claude --version; } >> $E/env.txt 2>&1
: > $E/m02-suite-x3.txt
for i in 1 2 3; do echo "=== run $i ($(date -u +%FT%TZ))" >> $E/m02-suite-x3.txt; $G python -m unittest discover -s tests/m02 -p 'test_gateway_*.py' -v >> $E/m02-suite-x3.txt 2>&1; echo "exit $?" >> $E/m02-suite-x3.txt; done
{ $G python tests/m01/check_no_secrets.py; echo "exit $?"; $G python tests/m01/test_m01_10_llm_check.py; echo "exit $?"; $G python tests/m01/test_m01_console.py; echo "exit $?"; } > $E/m01-regression-and-secret-scan.txt 2>&1
# stage-B runner on fake backends and on the real MCP client with local stand-ins
T=$(mktemp -d); $G python tests/m02/make_pilot_synthetic.py $T/syn > /dev/null
: > $E/fake-runs.txt
for f in clean mixed auth; do echo "=== fake:$f" >> $E/fake-runs.txt; $G python tests/m02/pilot_stage_b.py --fake $f --config $T/syn/gateway.pilot.stage-b.json --out $T/out-$f 2>&1 | grep -v "summary (committable)" >> $E/fake-runs.txt; echo "exit ${PIPESTATUS[0]}" >> $E/fake-runs.txt; done
rm -rf $T
: > $E/standin-runs.txt
for v in startup call; do $G python tests/m02/evidence/sandbox-linux-2026-10-09-contract-v2/standin_run.py $W $E $v >> $E/standin-runs.txt 2>&1; done
# real Claude Code, clean config dir (account-synced plugins excluded for the child only)
for i in 1; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean4 $G python tests/m02/m02_surface.py surface --out $E/raw > /dev/null 2>&1; echo "clean surface $i exit $?" >> $E/runs.txt; done
for i in 1 2; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean4 $G python tests/m02/m02_surface.py llm --out $E/raw > /dev/null 2>&1; echo "clean llm $i exit $?" >> $E/runs.txt; done
git status --porcelain --untracked-files=all > $E/worktree-status-after.txt
# revert check: the previous runtime file (eec1680) against the new F13/F14 tests
git show eec1680632162f3af869cbe99bc4492df19d2f5e:gateway/adapters/notebooklm.py > gateway/adapters/notebooklm.py
{ echo "revert: gateway/adapters/notebooklm.py from eec1680"; $G python -m unittest discover -s tests/m02 -p 'test_gateway_f13_f14.py' 2>&1 | grep -E "^(FAIL|ERROR):|^Ran|^FAILED|^OK"; } > $E/revert-check.txt
git checkout -- gateway/adapters/notebooklm.py
git status --porcelain --untracked-files=all > $E/worktree-status-after-revert-check.txt
echo done >> $E/runs.txt
