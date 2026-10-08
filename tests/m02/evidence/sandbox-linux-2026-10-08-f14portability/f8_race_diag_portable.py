import json, sys, tempfile, time
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path[:0] = [str(REPO), str(REPO / "tests/m02")]
from gateway.adapters.notebooklm import McpStdioNotebookLMClient, NotebookLMAdapter
from gateway.errors import GatewayError
bad = 0
for i in range(int(sys.argv[2])):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); cfg = d / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {"command": sys.executable,
            "args": [str(REPO / "tests/m02/fake_mcp_server.py"), "--log", str(d/"l"), "--times", str(d/"t"), "--call-delay", "0.35"]}}}))
        c = McpStdioNotebookLMClient(cfg, start_timeout_s=0.5)
        c._start_timeout = 30
        with c._lock: c._start()
        c._start_timeout = 0.5
        a = NotebookLMAdapter(c, timeout_s=0.05, max_attempts=2, total_budget_s=0.1, backoff_s=0.0)
        t0 = time.monotonic()
        try: a.query("nb", "q", ["s"])
        except GatewayError as e: code = e.code
        time.sleep(1.0)
        if c._proc is not None:
            bad += 1
            st = {"spawned": "n/a", "teardowns": [], "alive": c._proc.poll() is None, "ready": c._ready}
            print("BAD", i, "alive", st["alive"], "ready", st["ready"], "spawned", st["spawned"], "teardowns", st["teardowns"], "locked", c._lock.locked(), "log", (d/"l").read_text().split("\n"))
            time.sleep(5); print("   after 5s more: proc None?", c._proc is None, "teardowns", "n/a")
        c.close()
print("bad", bad)
