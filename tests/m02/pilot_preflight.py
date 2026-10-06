#!/usr/bin/env python3
"""M02 pilot stage-A preflight (docs/M02_PILOT_PLAN.md §6a). Windows only; metadata and hashes only.

Run non-elevated, as the account that runs Claude Code and the Gateway, right before and right after the stage-A
run. Nothing is written, opened for write, or changed (no ACL edit, no privilege change); there is no directory
listing. Only the parent, the source root and the three files named in the pilot INDEX are examined.

  token     the process token is not elevated, its integrity level is at most Medium, and it holds none of the
            privileges that bypass or rewrite ACLs (backup, restore, take-ownership, security, relabel,
            manage-volume, create-symlink).
  access    effective rights from the Windows AccessCheck API, evaluated with the real process token (all its user
            and group SIDs, deny-only groups and integrity label) and MAXIMUM_ALLOWED; no inference from single
            ACE lines. FAIL if any write/create/modify/delete/delete-child/permission-change/ownership right is
            granted: files and root -> any of them; parent -> delete-child, WRITE_DAC, WRITE_OWNER (creating
            unrelated folders next to the root is not a risk to it and is only recorded).
  files     each pilot file: regular file, no reparse point or Cloud Files placeholder/offline attribute, hard-link
            count 1, SHA-256 equal to the pilot INDEX. The root: a directory with no reparse/placeholder attribute.

Outputs under tests/m02/evidence/local/ (git-ignored): preflight-<phase>-<ts>.raw.json (SIDs, SDDL, masks; local
only) and preflight-<phase>-<ts>.summary.json (no SID, user name or SDDL; committable).
Exit code: 0 PASS, 1 FAIL, 2 cannot run (not Windows, config/INDEX unreadable). On FAIL: stop and report; do not
change ACLs, elevate, or change the adapter to get past it.

  uv run --no-project --python 3.11 --with pyyaml==6.0.2 --exclude-newer 2026-10-03T00:00:00Z \
      tests/m02/pilot_preflight.py --phase before
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from gateway.config import load_config  # noqa: E402
from gateway.index import load_index  # noqa: E402

CONFIG = REPO / "docs" / "m02-pilot" / "gateway.pilot.stage-a.json"

# access rights
FILE_READ_DATA, FILE_WRITE_DATA, FILE_APPEND_DATA = 0x1, 0x2, 0x4
FILE_WRITE_EA, FILE_DELETE_CHILD, FILE_WRITE_ATTRIBUTES = 0x10, 0x40, 0x100
DELETE, READ_CONTROL, WRITE_DAC, WRITE_OWNER = 0x10000, 0x20000, 0x40000, 0x80000
MAXIMUM_ALLOWED = 0x02000000
RIGHT_NAMES = {FILE_WRITE_DATA: "WRITE_DATA/ADD_FILE", FILE_APPEND_DATA: "APPEND_DATA/ADD_SUBDIRECTORY",
               FILE_WRITE_EA: "WRITE_EA", FILE_DELETE_CHILD: "DELETE_CHILD", FILE_WRITE_ATTRIBUTES: "WRITE_ATTRIBUTES",
               DELETE: "DELETE", WRITE_DAC: "WRITE_DAC", WRITE_OWNER: "WRITE_OWNER"}
WRITE_LIKE = sum(RIGHT_NAMES)
FORBIDDEN = {"file": WRITE_LIKE, "root": WRITE_LIKE, "parent": FILE_DELETE_CHILD | WRITE_DAC | WRITE_OWNER}
# file attributes
ATTR_DIRECTORY, ATTR_REPARSE, ATTR_OFFLINE = 0x10, 0x400, 0x1000
ATTR_RECALL_ON_OPEN, ATTR_UNPINNED, ATTR_RECALL_ON_DATA = 0x40000, 0x100000, 0x400000
BAD_ATTRS = {ATTR_REPARSE: "REPARSE_POINT", ATTR_OFFLINE: "OFFLINE", ATTR_RECALL_ON_OPEN: "RECALL_ON_OPEN",
             ATTR_UNPINNED: "UNPINNED", ATTR_RECALL_ON_DATA: "RECALL_ON_DATA_ACCESS"}
DANGEROUS_PRIVILEGES = {"SeBackupPrivilege", "SeRestorePrivilege", "SeTakeOwnershipPrivilege", "SeSecurityPrivilege",
                        "SeRelabelPrivilege", "SeManageVolumePrivilege", "SeCreateSymbolicLinkPrivilege",
                        "SeDebugPrivilege", "SeTcbPrivilege"}
INTEGRITY = {0x0000: "Untrusted", 0x1000: "Low", 0x2000: "Medium", 0x2100: "MediumPlus", 0x3000: "High",
             0x4000: "System"}


class GENERIC_MAPPING(ctypes.Structure):
    _fields_ = [("GenericRead", wintypes.DWORD), ("GenericWrite", wintypes.DWORD),
                ("GenericExecute", wintypes.DWORD), ("GenericAll", wintypes.DWORD)]


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [("dwFileAttributes", wintypes.DWORD), ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME), ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD), ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD), ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD), ("nFileIndexLow", wintypes.DWORD)]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]


class Win:
    """The few Win32 calls the preflight needs. Every handle is opened for query/read-attributes only."""

    def __init__(self):
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.adv = ctypes.WinDLL("advapi32", use_last_error=True)
        self.k32.GetCurrentProcess.restype = wintypes.HANDLE
        self.k32.CreateFileW.restype = wintypes.HANDLE
        self.k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        self.adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        self.adv.GetSidSubAuthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]
        self.adv.GetSidSubAuthorityCount.argtypes = [wintypes.LPVOID]
        H, D, P, LP = wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, ctypes.POINTER
        self.k32.CloseHandle.argtypes = [H]
        self.k32.LocalFree.argtypes = [P]
        self.k32.GetFileInformationByHandle.argtypes = [H, P]
        self.adv.OpenProcessToken.argtypes = [H, D, LP(H)]
        self.adv.GetTokenInformation.argtypes = [H, ctypes.c_int, P, D, LP(D)]
        self.adv.DuplicateToken.argtypes = [H, ctypes.c_int, LP(H)]
        self.adv.ConvertSidToStringSidW.argtypes = [P, LP(wintypes.LPWSTR)]
        self.adv.LookupPrivilegeNameW.argtypes = [wintypes.LPCWSTR, LP(LUID), wintypes.LPWSTR, LP(D)]
        self.adv.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, D, P, D, LP(D)]
        self.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            P, D, D, LP(wintypes.LPWSTR), LP(wintypes.ULONG)]
        self.adv.AccessCheck.argtypes = [P, H, D, LP(GENERIC_MAPPING), P, LP(D), LP(D), LP(wintypes.BOOL)]

    def _check(self, ok, what: str):
        if not ok:
            raise OSError(ctypes.get_last_error(), f"{what} failed")

    # -------------------------------------------------------------- token
    def process_token(self) -> wintypes.HANDLE:
        token = wintypes.HANDLE()
        TOKEN_QUERY, TOKEN_DUPLICATE = 0x0008, 0x0002
        self._check(self.adv.OpenProcessToken(self.k32.GetCurrentProcess(), TOKEN_QUERY | TOKEN_DUPLICATE,
                                              ctypes.byref(token)), "OpenProcessToken")
        return token

    def token_info(self, token, cls: int) -> ctypes.Array:
        size = wintypes.DWORD()
        self.adv.GetTokenInformation(token, cls, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        self._check(self.adv.GetTokenInformation(token, cls, buf, size, ctypes.byref(size)), "GetTokenInformation")
        return buf

    def sid_string(self, psid) -> str:
        out = wintypes.LPWSTR()
        self._check(self.adv.ConvertSidToStringSidW(psid, ctypes.byref(out)), "ConvertSidToStringSidW")
        try:
            return out.value
        finally:
            self.k32.LocalFree(out)

    def token_facts(self, token) -> dict:
        TokenUser, TokenPrivileges, TokenElevationType, TokenElevation, TokenIntegrityLevel = 1, 3, 18, 20, 25
        user = self.token_info(token, TokenUser)
        user_sid = self.sid_string(ctypes.c_void_p.from_buffer(user).value)
        elevated = wintypes.DWORD.from_buffer(self.token_info(token, TokenElevation)).value
        etype = wintypes.DWORD.from_buffer(self.token_info(token, TokenElevationType)).value
        label = self.token_info(token, TokenIntegrityLevel)
        psid = ctypes.c_void_p.from_buffer(label).value
        count = self.adv.GetSidSubAuthorityCount(psid).contents.value
        rid = self.adv.GetSidSubAuthority(psid, count - 1).contents.value
        privs_buf = self.token_info(token, TokenPrivileges)
        n = wintypes.DWORD.from_buffer(privs_buf).value
        arr = (LUID_AND_ATTRIBUTES * n).from_buffer(privs_buf, ctypes.sizeof(wintypes.DWORD))
        privileges = []
        for item in arr:
            name_len = wintypes.DWORD(0)
            self.adv.LookupPrivilegeNameW(None, ctypes.byref(item.Luid), None, ctypes.byref(name_len))
            name = ctypes.create_unicode_buffer(name_len.value + 1)
            name_len = wintypes.DWORD(len(name))
            self._check(self.adv.LookupPrivilegeNameW(None, ctypes.byref(item.Luid), name, ctypes.byref(name_len)),
                        "LookupPrivilegeNameW")
            privileges.append({"name": name.value, "enabled": bool(item.Attributes & 0x2)})
        return {"user_sid": user_sid, "elevated": bool(elevated),
                "elevation_type": {1: "Default", 2: "Full", 3: "Limited"}.get(etype, str(etype)),
                "integrity_rid": rid, "integrity": INTEGRITY.get(rid, hex(rid)), "privileges": privileges}

    def impersonation_token(self, token) -> wintypes.HANDLE:
        imp = wintypes.HANDLE()
        self._check(self.adv.DuplicateToken(token, 2, ctypes.byref(imp)), "DuplicateToken")   # SecurityImpersonation
        return imp

    # -------------------------------------------------------------- objects
    def security_descriptor(self, path: str) -> ctypes.Array:
        info = 0x1 | 0x2 | 0x4 | 0x10   # OWNER | GROUP | DACL | LABEL (needs READ_CONTROL only)
        size = wintypes.DWORD()
        self.adv.GetFileSecurityW(path, info, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        self._check(self.adv.GetFileSecurityW(path, info, buf, size, ctypes.byref(size)), "GetFileSecurityW")
        return buf

    def sddl(self, sd) -> str:
        out, n = wintypes.LPWSTR(), wintypes.ULONG()
        self._check(self.adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            sd, 1, 0x1 | 0x2 | 0x4 | 0x10, ctypes.byref(out), ctypes.byref(n)), "ConvertSD")
        try:
            return out.value
        finally:
            self.k32.LocalFree(out)

    def granted(self, imp_token, sd) -> int:
        mapping = GENERIC_MAPPING(0x120089, 0x120116, 0x1200A0, 0x1F01FF)   # FILE_GENERIC_*, FILE_ALL_ACCESS
        privset = ctypes.create_string_buffer(256)
        plen = wintypes.DWORD(256)
        granted, status = wintypes.DWORD(), wintypes.BOOL()
        self._check(self.adv.AccessCheck(sd, imp_token, MAXIMUM_ALLOWED, ctypes.byref(mapping), privset,
                                         ctypes.byref(plen), ctypes.byref(granted), ctypes.byref(status)),
                    "AccessCheck")
        return granted.value if status.value else 0

    def handle_info(self, path: str) -> BY_HANDLE_FILE_INFORMATION:
        FILE_READ_ATTRIBUTES, SHARE_ALL, OPEN_EXISTING = 0x80, 0x7, 3
        flags = 0x02000000 | 0x00200000   # BACKUP_SEMANTICS (open directories) | OPEN_REPARSE_POINT (no follow)
        h = self.k32.CreateFileW(path, FILE_READ_ATTRIBUTES, SHARE_ALL, None, OPEN_EXISTING, flags, None)
        if h in (None, wintypes.HANDLE(-1).value):
            raise OSError(ctypes.get_last_error(), "CreateFileW (read attributes) failed")
        try:
            info = BY_HANDLE_FILE_INFORMATION()
            self._check(self.k32.GetFileInformationByHandle(h, ctypes.byref(info)), "GetFileInformationByHandle")
            return info
        finally:
            self.k32.CloseHandle(h)


def rights(mask: int) -> list[str]:
    return [name for bit, name in RIGHT_NAMES.items() if mask & bit]


def attrs(mask: int) -> list[str]:
    return [name for bit, name in BAD_ATTRS.items() if mask & bit]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:   # read-only
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30).stdout.strip()
    except OSError:
        return None


def run_checks(config: Path) -> tuple[dict, dict]:
    cfg = load_config(config)
    index = load_index(cfg.index_path)
    root = Path(cfg.source_root)
    targets = [("parent", root.parent), ("root", root)]
    expected = {}
    for doc in index.documents.values():
        for v in doc.versions:
            targets.append(("file", root / v.path))
            expected[str(root / v.path)] = v.sha256

    win = Win()
    token = win.process_token()
    facts = win.token_facts(token)
    imp = win.impersonation_token(token)
    held = {p["name"] for p in facts["privileges"]}
    checks, raw_objects, summary_objects = [], [], []
    checks.append({"name": "TOKEN_NOT_ELEVATED", "result": "PASS" if not facts["elevated"] else "FAIL",
                   "detail": f"elevated={facts['elevated']} type={facts['elevation_type']}"})
    checks.append({"name": "TOKEN_INTEGRITY_AT_MOST_MEDIUM",
                   "result": "PASS" if facts["integrity_rid"] <= 0x2000 else "FAIL", "detail": facts["integrity"]})
    bad_privs = sorted(held & DANGEROUS_PRIVILEGES)
    checks.append({"name": "NO_ACL_BYPASS_PRIVILEGES", "result": "FAIL" if bad_privs else "PASS",
                   "detail": ",".join(bad_privs) or "none held"})

    for kind, path in targets:
        obj = {"kind": kind, "name": path.name or str(path)}
        problems = []
        try:
            sd = win.security_descriptor(str(path))
            mask = win.granted(imp, sd)
            info = win.handle_info(str(path))
        except OSError as e:
            obj["error"] = f"winerror {e.args[0]}"
            checks.append({"name": f"OBJECT_{kind.upper()}", "result": "FAIL",
                           "detail": f"{obj['name']}: cannot evaluate ({obj['error']})"})
            raw_objects.append(dict(obj))
            summary_objects.append(obj)
            continue
        forbidden = rights(mask & FORBIDDEN[kind])
        obj.update(granted_mask=hex(mask), write_like_rights=rights(mask), forbidden_rights=forbidden,
                   can_read=bool(mask & FILE_READ_DATA), attributes=hex(info.dwFileAttributes),
                   bad_attributes=attrs(info.dwFileAttributes))
        if forbidden:
            problems.append("forbidden rights " + ",".join(forbidden))
        if kind != "parent" and obj["bad_attributes"]:
            problems.append("attributes " + ",".join(obj["bad_attributes"]))
        if kind == "root" and not info.dwFileAttributes & ATTR_DIRECTORY:
            problems.append("root is not a directory")
        if kind == "file":
            obj.update(hard_links=info.nNumberOfLinks, bytes=(info.nFileSizeHigh << 32) | info.nFileSizeLow,
                       is_directory=bool(info.dwFileAttributes & ATTR_DIRECTORY))
            if obj["is_directory"]:
                problems.append("not a regular file")
            if info.nNumberOfLinks != 1:
                problems.append(f"hard-link count {info.nNumberOfLinks}")
            if not obj["can_read"]:
                problems.append("not readable")
            if not problems:
                obj["sha256"] = sha256(path)
                obj["sha256_matches_index"] = obj["sha256"] == expected[str(path)]
                if not obj["sha256_matches_index"]:
                    problems.append("SHA-256 differs from the pilot INDEX")
        checks.append({"name": f"OBJECT_{kind.upper()}", "result": "FAIL" if problems else "PASS",
                       "detail": f"{obj['name']}: " + ("; ".join(problems) or "ok")})
        summary_objects.append(dict(obj))
        obj["sddl"] = win.sddl(sd)
        raw_objects.append(obj)

    win.k32.CloseHandle(imp)
    win.k32.CloseHandle(token)
    token_summary = {k: v for k, v in facts.items() if k != "user_sid"}
    token_summary["dangerous_privileges_held"] = bad_privs
    summary = {"token": token_summary, "objects": summary_objects, "checks": checks}
    raw = {"token": facts, "objects": raw_objects, "checks": checks}
    return summary, raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=("before", "after"), required=True)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--out", type=Path, default=HERE / "evidence" / "local")
    args = ap.parse_args()
    started = dt.datetime.now(dt.timezone.utc)
    head = {"check": f"m02-stage-a-preflight-{args.phase}", "utc": started.isoformat(timespec="seconds"),
            "head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "",
            "python": platform.python_version(), "platform": platform.platform()}
    if sys.platform != "win32":
        print(json.dumps({**head, "status": "CANNOT_RUN", "reason": "Windows only"}, indent=2))
        return 2
    try:
        summary, raw = run_checks(args.config.resolve())
    except Exception as e:   # config/INDEX unreadable or a Win32 call outside the per-object checks
        print(json.dumps({**head, "status": "CANNOT_RUN", "reason": f"{type(e).__name__}: {e}"}, indent=2))
        return 2
    status = "PASS" if all(c["result"] == "PASS" for c in summary["checks"]) else "FAIL"
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (args.out / f"preflight-{args.phase}-{stamp}.raw.json").write_text(
        json.dumps({**head, "status": status, **raw}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sum_path = args.out / f"preflight-{args.phase}-{stamp}.summary.json"
    sum_path.write_text(json.dumps({**head, "status": status, **summary}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    sys.stdout.reconfigure(errors="backslashreplace")
    for c in summary["checks"]:
        print(f"{c['result']:4}  {c['name']:32} {c['detail']}")
    print(f"PREFLIGHT {args.phase.upper()}: {status}")
    print(f"[preflight] summary (committable): {sum_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
