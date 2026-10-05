"""Fake NotebookLM backend for offline contract tests (implements the four M01 read operations).

It never talks to Google. Scripted answers are keyed by notebook; failures can be injected.
"""
from __future__ import annotations

import time


class FakeNotebookLM:
    def __init__(self, answers: dict | None = None):
        # answers: notebook_id -> {"answer": str, "citations": [{"source_id", "passage"}], "sources_used": [...]}
        self.answers = answers or {}
        self.calls: list[tuple] = []
        self.fail_with: list[dict] = []     # queued error payloads returned before succeeding
        self.raise_with: list[BaseException] = []
        self.delay_s = 0.0

    def _record(self, *call):
        self.calls.append(call)
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.raise_with:
            raise self.raise_with.pop(0)
        if self.fail_with:
            return self.fail_with.pop(0)
        return None

    def notebook_list(self) -> dict:
        return self._record("notebook_list") or {"status": "success", "notebooks": [{"id": "nb-fixture-001"}]}

    def notebook_get(self, notebook_id: str) -> dict:
        return self._record("notebook_get", notebook_id) or {"status": "success", "sources": []}

    def source_get_content(self, source_id: str) -> dict:
        return self._record("source_get_content", source_id) or {"status": "error", "error": "not simulated"}

    def notebook_query(self, notebook_id: str, query: str, source_ids: list[str]) -> dict:
        failed = self._record("notebook_query", notebook_id, query, tuple(source_ids))
        if failed:
            return failed
        return {"status": "success", **self.answers.get(notebook_id, {"answer": "", "citations": []})}
