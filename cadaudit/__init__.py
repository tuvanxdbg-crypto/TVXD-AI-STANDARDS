"""cadaudit: read-only CAD audit on pre-extracted CAD_READ JSON (docs/M04_CAD_AUDIT_READONLY.md).

Offline. No AutoCAD, no DWG/DXF, no network, no NotebookLM or Gateway call. The only module that writes a file is
cadaudit/_report_writer.py, and it only ever creates a new file.
"""
__version__ = "0.1.0-m04a"
