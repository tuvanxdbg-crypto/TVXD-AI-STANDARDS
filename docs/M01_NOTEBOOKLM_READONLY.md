# M01 — NotebookLM content-read-only pilot

## Objective
Prove that Claude Code can retrieve information from the company's current NotebookLM Pro account through MCP without allowing content-management or sharing mutations.

## Acceptance tests

| ID | Test | Expected |
|---|---|---|
| M01-01 | MCP server starts | PASS |
| M01-02 | Authentication check | PASS |
| M01-03 | List notebooks | PASS |
| M01-04 | Inspect one notebook + sources | PASS |
| M01-05 | Read one source's raw/text content | PASS |
| M01-06 | Query one notebook | PASS |
| M01-07 | Verify only approved tools are exposed | PASS |
| M01-08 | Attempt to access a disallowed mutation capability | BLOCKED / unavailable |
| M01-09 | No credentials or auth artifacts tracked by Git | PASS |

## Approved tool surface
- notebook_list
- notebook_get
- source_get_content
- notebook_query

## Read-only boundary
M01 protects notebook/source content and sharing configuration from mutation.

The approved query tool may persist chat history in NotebookLM. This is an accepted pilot side effect and must not be confused with permission to edit notebook/source content.

## Local installation
Install and authenticate the community NotebookLM MCP on the Windows machine that runs Claude Code. Authentication must be completed locally by the user; credentials must never be pasted into GitHub, issues, PR comments, or chat.

After installation, verify the executable and the exact exposed tool names on that machine before committing a project-scoped MCP config. Do not guess executable paths.

## Tool exposure policy
The local MCP configuration must hide all NotebookLM tool groups except the minimum needed for M01, then explicitly enable only the four approved tools.

See:
- `config/m01-tool-policy.yaml`
- `tests/m01/ACCEPTANCE.md`

## Exit criteria
M01 is complete only when all tests are PASS/BLOCKED as expected and the PR contains evidence of the actual tool surface.

M01 does not authorize:
- standards applicability decisions;
- legal-validity conclusions;
- CAD audit;
- CAD write operations;
- M02 Gateway development.

## Dependency risk
The current community MCP relies on non-public NotebookLM interfaces. Treat it as a pilot dependency. M02's Gateway must isolate Claude from this backend so it can later be replaced without changing Claude's public tool contract.
