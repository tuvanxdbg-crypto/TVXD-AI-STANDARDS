set -u
S=<scratch>
W=$S/wt-d007; E=$S/ev4; SHA=d007e4e8e13839d1d96c92e236e0c41c9dbf411f
G="uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z"
cd $W
echo "worktree HEAD $(git rev-parse HEAD)" > $E/env.txt
{ uv --version; $G python --version; $G python -c 'import yaml;print("PyYAML",yaml.__version__)'; } >> $E/env.txt 2>&1
: > $E/m02-suite-x3.txt
for i in 1 2 3; do echo "=== run $i ($(date -u +%FT%TZ))" >> $E/m02-suite-x3.txt; $G python -m unittest discover -s tests/m02 -p 'test_gateway_*.py' -v >> $E/m02-suite-x3.txt 2>&1; echo "exit $?" >> $E/m02-suite-x3.txt; done
{ $G python tests/m01/check_no_secrets.py; echo "exit $?"; $G python tests/m01/test_m01_10_llm_check.py; echo "exit $?"; $G python tests/m01/test_m01_console.py; echo "exit $?"; } > $E/m01-regression-and-secret-scan.txt 2>&1
T=$(mktemp -d); $G python tests/m02/make_pilot_synthetic.py $T/syn > /dev/null
: > $E/fake-runs.txt
for f in clean mixed auth; do echo "=== fake:$f" >> $E/fake-runs.txt; $G python tests/m02/pilot_stage_b.py --fake $f --config $T/syn/gateway.pilot.stage-b.json --out $T/out-$f 2>&1 | grep -v "summary (committable)" >> $E/fake-runs.txt; echo "exit ${PIPESTATUS[0]}" >> $E/fake-runs.txt; done
rm -rf $T
: > $E/preflight-v2-runs.txt
for spec in "before $SHA committed-stage-b-config" "before 0000000000000000000000000000000000000000 wrong-expect-head"; do set -- $spec
  echo "=== phase $1, --expect-head $2 ($3)" >> $E/preflight-v2-runs.txt
  $G python tests/m02/pilot_stage_b_v2_preflight.py --phase $1 --expect-head $2 --out $E/pf 2>&1 | grep -v "summary (committable)" >> $E/preflight-v2-runs.txt; echo "exit ${PIPESTATUS[0]}" >> $E/preflight-v2-runs.txt; done
git status --porcelain --untracked-files=all > $E/worktree-status-after.txt
echo done > $E/done.txt
