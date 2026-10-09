set -u
S=<scratch>
W=$S/wt-d026; E=$S/ev
G="uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z"
cd $W
echo "worktree HEAD $(git rev-parse HEAD)" > $E/env.txt
{ uv --version; $G python --version; $G python -c 'import yaml;print("PyYAML",yaml.__version__)'; claude --version; } >> $E/env.txt 2>&1
: > $E/m02-suite-x3.txt
for i in 1 2 3; do echo "=== run $i ($(date -u +%FT%TZ))" >> $E/m02-suite-x3.txt; $G python -m unittest discover -s tests/m02 -p 'test_gateway_*.py' -v >> $E/m02-suite-x3.txt 2>&1; echo "exit $?" >> $E/m02-suite-x3.txt; done
{ $G python tests/m01/check_no_secrets.py; echo "exit $?"; $G python tests/m01/test_m01_10_llm_check.py; echo "exit $?"; $G python tests/m01/test_m01_console.py; echo "exit $?"; } > $E/m01-regression-and-secret-scan.txt 2>&1
# Observation: default config dir with account-synced plugins
$G python tests/m02/m02_surface.py surface --out $E/raw-synced > /dev/null 2>&1; echo "synced-plugins surface exit $?" >> $E/runs.txt
mkdir -p $S/claude-config-clean2
for i in 1 2; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean2 $G python tests/m02/m02_surface.py surface --out $E/raw > /dev/null 2>&1; echo "clean surface $i exit $?" >> $E/runs.txt; done
for i in 1 2 3; do env -u CLAUDE_CODE_SYNC_PLUGINS -u CLAUDE_CODE_SYNC_SKILLS CLAUDE_CONFIG_DIR=$S/claude-config-clean2 $G python tests/m02/m02_surface.py llm --out $E/raw > /dev/null 2>&1; echo "clean llm $i exit $?" >> $E/runs.txt; done
git status --porcelain --untracked-files=all > $E/worktree-status-after.txt
echo done >> $E/runs.txt
