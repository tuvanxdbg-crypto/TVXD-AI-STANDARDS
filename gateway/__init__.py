"""TVXD Standards Gateway (M02).

Claude Code sees exactly three MCP tools: standards_lookup, standards_verify and
standards_status. Contract v2 (OWNER_ARCHITECTURE_CHANGE_V1, M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE):
INDEX defines scope and applicability, and NotebookLM, used only through the four M01-approved
read tools and limited to the whitelisted notebook/sources, is the primary source, trusted by
owner policy. See docs/M02_STANDARDS_GATEWAY.md.
"""
GATEWAY_VERSION = "0.2.0"
PUBLIC_TOOLS = ("standards_lookup", "standards_verify", "standards_status")
CONTRACT_VERSION = "v2"
EVIDENCE_CONTRACT = "tvxd.gateway.evidence/v2"
TRUST_POLICY = "M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE"
