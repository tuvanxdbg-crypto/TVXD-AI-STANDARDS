"""TVXD Standards Gateway (M02, offline-first).

Claude Code sees exactly three MCP tools: standards_lookup, standards_verify and
standards_status. Behind them: INDEX (machine metadata), a read-only local source
adapter over the Nextcloud sync/mount, and a NotebookLM semantic adapter that uses
only the four M01-approved read tools. See docs/M02_STANDARDS_GATEWAY.md.
"""
GATEWAY_VERSION = "0.1.0"
PUBLIC_TOOLS = ("standards_lookup", "standards_verify", "standards_status")
