# B2 findings F13 and F14: offline reproduction (sandbox Linux, 2026-10-07)

`repro_b2.py` runs offline at `67874a3` with no Google contact. It uses the unchanged Gateway code. Output from 3
runs: `repro_b2.out.txt`.

Command:
```
uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \
    python tests/m02/evidence/sandbox-linux-2026-10-07-b2-analysis/repro_b2.py "$PWD"
```

1. **F13, citation shape.**
   - A fake client returns the `notebooklm-mcp-cli==0.15.1` `notebook_query` shape:
     - `citations`: `{"1": id, "2": id}` (JSON turns the int keys into strings);
     - `references`: `[{source_id, citation_number, cited_text}]`;
     - `sources_used`: `[id]`.
   - Every id is one of the three queried ids.
   - `NotebookLMAdapter.query` returns `out_of_scope_source_ids == ["<unattributed>"]`, no answer and no citations.
     This is the live B2 behaviour.
2. **F14, P8 sampling.**
   - `McpStdioNotebookLMClient` is run against `tests/m02/fake_mcp_server.py --init-delay 2.5`, with a 1 s budget.
   - The caller gets `TIMEOUT` at 1.00 s. On Linux the process is already gone when sampled right after the
     timeout. The server log shows one `start` and no `tools/call`.
   - The live Windows run sampled a live process at that point, while its worker ran on until 3077 ms. So the
     check is timing-dependent, and this reproduction does not show the Windows interleaving.

Not changed: Gateway code, runner, configs. The fixes are proposed in the B2 report for review first.
