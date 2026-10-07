"""Offline: the B2 runner against the real MCP client and fake_uvx_wrapper.py -> fake_mcp_server.py."""
import json, sys, tempfile
from pathlib import Path
REPO = Path(sys.argv[1]); OUT = Path(sys.argv[2]); variant = sys.argv[3]
sys.path[:0] = [str(REPO / "tests/m02"), str(REPO)]
import pilot_stage_b as sb
from gateway.adapters.notebooklm import McpStdioNotebookLMClient
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    import subprocess
    subprocess.run([sys.executable, str(REPO / "tests/m02/make_pilot_synthetic.py"), str(d / "syn")], check=True, capture_output=True)
    (d / "answer.json").write_text(json.dumps(sb.fake_answer("clean"), ensure_ascii=False), encoding="utf-8")
    def cfg(name, *opts):
        p = d / name
        p.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {"command": sys.executable, "args": [
            str(REPO / "tests/m02/fake_uvx_wrapper.py"), "--pid-file", str(d / "child.pids"), "--", sys.executable,
            str(REPO / "tests/m02/fake_mcp_server.py"), "--answer-file", str(d / "answer.json"), *opts]}}}))
        return p
    slow = (("--init-delay", "2.5", "--delay-once", str(d / "once")) if variant == "startup"
            else ("--call-delay", "3", "--call-delay-once", str(d / "once")))
    main_cfg, slow_cfg = cfg("main.json"), cfg("slow.json", *slow)
    code, s = sb.execute(d / "syn" / "gateway.pilot.stage-b.json",
                         lambda slow=False: McpStdioNotebookLMClient(slow_cfg if slow else main_cfg, start_timeout_s=10),
                         kind=f"stand-in:{variant}", out=d / "out")
    text = Path(s["summary_file"]).read_text(encoding="utf-8").replace(str(d), "<tmp>")
    (OUT / f"standin-{variant}-stage-b.summary.json").write_text(text, encoding="utf-8")
    print(variant, code, s["status"], {c["id"]: c["result"] for c in s["cases"]})
