set -u
S=<scratch>
W=$S/wt-fa1a; E=$S/ev2
G="uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z"
cd $W
echo "worktree HEAD $(git rev-parse HEAD)" > $E/env.txt
{ uv --version; $G python --version; $G python -c 'import yaml;print("PyYAML",yaml.__version__)'; claude --version; } >> $E/env.txt 2>&1
: > $E/m02-suite-x3.txt
for i in 1 2 3; do echo "=== run $i ($(date -u +%FT%TZ))" >> $E/m02-suite-x3.txt; $G python -m unittest discover -s tests/m02 -p 'test_gateway_*.py' -v >> $E/m02-suite-x3.txt 2>&1; echo "exit $?" >> $E/m02-suite-x3.txt; done
{ $G python tests/m01/check_no_secrets.py; echo "exit $?"; $G python tests/m01/test_m01_10_llm_check.py; echo "exit $?"; $G python tests/m01/test_m01_console.py; echo "exit $?"; } > $E/m01-regression-and-secret-scan.txt 2>&1
# Observation: default config dir with account-synced plugins
$G python tests/m02/m02_surface.py surface --out $E/raw-synced > /dev/null 2>&1; echo "synced-plugins surface exit $?" >> $E/runs.txt
mkdir -p $S/claude-config-clean3
for i in 1 2; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean3 $G python tests/m02/m02_surface.py surface --out $E/raw > /dev/null 2>&1; echo "clean surface $i exit $?" >> $E/runs.txt; done
for i in 1 2 3; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean3 $G python tests/m02/m02_surface.py llm --out $E/raw > /dev/null 2>&1; echo "clean llm $i exit $?" >> $E/runs.txt; done
git status --porcelain --untracked-files=all > $E/worktree-status-after.txt
# Revert check, in this worktree: restore the pre-review PASS rules, run the harness tests, restore the file.
python3 - <<'PY'
from pathlib import Path
p = Path("tests/m02/m02_surface.py"); s = p.read_text()
a = '"exactly_one_lookup_and_no_other_tool": trace_ok(uses),'
b = '"fake_notebooklm_exactly_one_query": calls == ["notebook_query"],'
assert a in s and b in s
s = s.replace(a, '"exactly_one_lookup_and_no_other_tool": all(allowed_use(u) for u in uses),')
s = s.replace(b, '"fake_notebooklm_exactly_one_query": bool(calls) and set(calls) == {"notebook_query"},')
p.write_text(s)
PY
{ echo "revert: trace rule -> all(allowed_use), backend list -> set (the 62a3828 rules)"; $G python -m unittest discover -s tests/m02 -p 'test_gateway_surface_harness.py' 2>&1 | grep -E "^(FAIL|ERROR):|^Ran|^FAILED|^OK"; } > $E/revert-check.txt
git checkout -- tests/m02/m02_surface.py
git status --porcelain --untracked-files=all > $E/worktree-status-after-revert-check.txt
echo done >> $E/runs.txt
