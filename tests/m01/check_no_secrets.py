#!/usr/bin/env python3
"""M01-09: no credentials or NotebookLM auth artifacts are tracked by Git.

Minimal local check (standard library only). Full secret scanning stays in M03.

1. No tracked file has a credential-like name.
2. No tracked file contains Google session cookies, tokens or private keys.
3. The local auth locations are ignored by .gitignore.

Usage (from the repo root):  python tests/m01/check_no_secrets.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FORBIDDEN_NAMES = [
    r"(^|/)auth[^/]*\.json$",
    r"(^|/)cookies?[^/]*\.(json|txt)$",
    r"(^|/)credentials[^/]*\.json$",
    r"(^|/)\.env(\.[^/]*)?$",
    r"(^|/)settings\.local\.json$",
    r"(^|/)\.notebooklm-mcp-cli/",
    r"(^|/)\.tvxd-notebooklm-mcp-cli/",
    r"(^|/)chrome-profiles?/",
    r"(^|/)browser-profile/",
    r"(^|/)tests/m01/evidence/local/",
    r"\.(pem|p12|pfx|key)$",
]

# Each pattern requires a value after the marker, so the pattern text itself never matches.
SECRET_CONTENT = {
    "google_session_cookie": r"\b(__Secure-[13]PSID[A-Z]*|SAPISID|APISID|HSID|SSID|SID)\s*[=:]\s*\"?[A-Za-z0-9_\-./]{20,}",
    "google_oauth_token": r"\bya29\.[A-Za-z0-9_\-]{20,}",
    "google_api_key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "anthropic_key": r"\bsk-ant-[A-Za-z0-9_\-]{20,}",
    "github_token": r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}",
    "private_key_block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*[A-Za-z0-9+/=]{40,}",
    "netscape_cookie_line": r"\.google\.com\t(TRUE|FALSE)\t/\t(TRUE|FALSE)\t\d+\t\w+\t\S{20,}",
}

MUST_BE_IGNORED = [
    ".notebooklm-mcp-cli/profiles/default/cookies.json",
    ".tvxd-notebooklm-mcp-cli/auth.json",
    "cookies.txt",
    "auth.json",
    ".env",
    ".claude/settings.local.json",
    "tests/m01/evidence/local/m01-probe-full.json",
]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def main() -> int:
    files = [f for f in git("ls-files", "-z").stdout.split("\0") if f]
    problems: list[str] = []

    for f in files:
        for pat in FORBIDDEN_NAMES:
            if re.search(pat, f):
                problems.append(f"forbidden file name tracked: {f}")

    for f in files:
        path = REPO / f
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IsADirectoryError):
            continue
        for label, pat in SECRET_CONTENT.items():
            if re.search(pat, text):
                problems.append(f"{label} pattern in tracked file: {f}")

    for p in MUST_BE_IGNORED:
        if git("check-ignore", "-q", "--no-index", p).returncode != 0:
            problems.append(f"not ignored by .gitignore: {p}")

    print(f"M01-09 scanned {len(files)} tracked files at {git('rev-parse', 'HEAD').stdout.strip()}")
    if problems:
        print("M01-09: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("M01-09: PASS (no credential-like names, no secret patterns, auth paths ignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
