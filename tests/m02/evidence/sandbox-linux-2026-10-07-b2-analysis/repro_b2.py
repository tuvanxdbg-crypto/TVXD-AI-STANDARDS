"""Offline reproduction of the two B2 findings (no Google contact)."""
import json, sys, tempfile, time
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path.insert(0, str(REPO))
from gateway.adapters.notebooklm import McpStdioNotebookLMClient, NotebookLMAdapter
from gateway.errors import GatewayError

A, B, C = "8b75af2d-4477-40fb-a67f-3ee10173c221", "8ccb8115-f552-4ecb-b42a-f0ee093f1d08", "d54bb084-5c50-4cef-8979-6e909f791c1e"
NB = "8ca84143-c240-4fcb-98fe-e1f8c6cca02d"

# 1. citation shape of notebooklm-mcp-cli 0.15.1 (services/chat.py, core/conversation.py), after JSON: int keys -> str
class Shape:
    def notebook_query(self, nb, q, ids):
        return {"status": "success", "answer": "x [1] [2]", "question": q, "conversation_id": "c",
                "sources_used": [B], "citations": {"1": B, "2": B},
                "references": [{"source_id": B, "citation_number": 1, "cited_text": "t"},
                               {"source_id": B, "citation_number": 2}]}
r = NotebookLMAdapter(Shape(), timeout_s=5, max_attempts=1, total_budget_s=5).query(NB, "q", [A, B, C])
print("shape: out_of_scope", r.out_of_scope_source_ids, "answer_kept", bool(r.answer), "citations", len(r.citations))

# 2. P8 race: 1 s budget while the server is still starting
with tempfile.TemporaryDirectory() as d:
    d = Path(d); log = d / "log"
    cfg = d / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"gemini-notebook-mcp": {"command": sys.executable,
        "args": [str(REPO / "tests/m02/fake_mcp_server.py"), "--log", str(log), "--init-delay", "2.5"]}}}))
    c = McpStdioNotebookLMClient(cfg)
    ad = NotebookLMAdapter(c, timeout_s=1, max_attempts=1, total_budget_s=1)
    t0 = time.monotonic()
    try:
        ad.query(NB, "q", [A, B, C])
    except GatewayError as e:
        print(f"p8: caller got {e.code} after {time.monotonic()-t0:.2f}s")
    p = c._proc
    print("p8: right after TIMEOUT: proc alive =", p is not None and p.poll() is None)
    time.sleep(3)
    p2 = c._proc
    print("p8: 3 s later: client._proc is None =", p2 is None, "| old proc exited =", p is None or p.poll() is not None)
    print("p8: server log:", log.read_text().split() if log.exists() else [])
    c.close()
