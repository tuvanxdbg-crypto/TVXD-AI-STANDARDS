#!/usr/bin/env python3
"""M04-B: tạo BẢN TÓM TẮT để đưa vào repo (docs/M04_B_PLAN.md mục 5 "Bản tóm tắt", quyết định B1).

Chạy trên máy người dùng sau `python -m cadaudit check` và sau `scripts/m04b/kiem_truy_vet.py`. Đầu vào là bốn
tệp: CAD_READ, tệp quy tắc, báo cáo `cadaudit` và output của phép kiểm truy vết (G7). Offline, chỉ đọc bốn tệp đó,
chỉ tạo MỘT tệp mới (`--out`, chế độ `xb`, không ghi đè).

Mục đích: không để dữ liệu bản vẽ lọt vào repo. Output chỉ gồm hash, số đếm, mã (enum) và `rule_id`; được dựng từ
danh sách trường cố định (không sao chép nguyên khối từ báo cáo hay CAD_READ). Mọi chuỗi đi vào output đều là một
giá trị enum, hex, nhãn phiên bản (không có ký tự điều khiển) hoặc `rule_id` đúng dạng. Không có `drawing`, handle,
tên layer hay xref, `results[]`, `actual`/`expected`, evidence ID, `note` tự do hay đường dẫn.

Script không import `cadaudit` và không import `kiem_truy_vet`; chỉ dùng thư viện chuẩn. Bản tóm tắt chỉ mô tả,
không thay cho phép kiểm truy vết: kết luận của G7 được chép nguyên (kể cả KHONG_DAT), không tự tính lại.

Kiểm đầu vào (sai một điều là exit 2, không ghi gì, thông điệp không chứa đường dẫn):
  - sha256 tính được của CAD_READ, quy tắc, báo cáo bằng ba giá trị ghim;
  - JSON của CAD_READ, báo cáo và tệp kiểm truy vết parse chặt (khóa trùng, NaN/Infinity bị từ chối);
  - kiểm truy vết: `schema` đúng, ba `sha256.*.tinh_duoc` bằng ba hash vừa tính, `buoc_da_chay` đủ 1..7;
  - báo cáo: `schema` đúng, `rules_file.sha256` bằng hash tệp quy tắc, `input.input_sha256` bằng hash CAD_READ;
  - các trường được đọc có đúng kiểu và đúng enum; `--cadaudit-sha` đúng 40 hex; `--out` chưa tồn tại.

Exit: 0 đã ghi output (kể cả khi kiểm truy vết KHONG_DAT); 2 lỗi đầu vào (không ghi gì); 70 lỗi nội bộ (không ghi gì).

  python scripts/m04b/tom_tat.py --cad-read P --rules P --report P --kiem-truy-vet P \\
      --sha256-cad-read H --sha256-rules H --sha256-report H --cadaudit-sha <40 hex> --out P
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

OUT_SCHEMA = "tvxd.m04b.tom_tat/v1"
KTV_SCHEMA = "tvxd.m04b.kiem_truy_vet/v1"
REPORT_SCHEMA = "tvxd.cadaudit.report/v1"

EXIT_OK, EXIT_INPUT, EXIT_INTERNAL = 0, 2, 70
MAX_CAD_READ_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 512 * 1024 * 1024
MAX_RULES_BYTES = 1024 * 1024
MAX_KTV_BYTES = 64 * 1024 * 1024

VERDICTS = ("PASS", "FAIL", "UNKNOWN")
RULE_STATUSES = ("FIXTURE", "PROPOSED", "APPROVED")
CLASSIFICATIONS = ("INTERNAL_ONLY", "STANDARD_REQUIRED")
OVERALLS = ("HAS_FAIL", "HAS_UNKNOWN", "ALL_RULES_PASS")
UNKNOWN_REASONS = ("COVERAGE_INCOMPLETE", "FIELD_MISSING", "STANDARD_LOOKUP_NOT_ENABLED", "NO_OBJECTS_IN_SCOPE")
COVERAGE_STATUSES = ("COMPLETE", "INCOMPLETE", "NOT_EXTRACTED")
COVERAGE_REASONS = ("XREF_DEPENDENT", "READ_ERROR", "TIMEOUT", "PARTIAL_ENUMERATION", "NOT_REQUESTED")
COVERAGE_GROUPS = ("layers", "xrefs")
STEPS = ["1", "2", "3", "4", "5", "6", "7"]
SHA_KEYS = (("cad_read", "SHA256_CAD_READ_SAI"), ("quy_tac", "SHA256_QUY_TAC_SAI"), ("bao_cao", "SHA256_BAO_CAO_SAI"))
OVERALL_NOTE = "RULES_NOT_APPROVED"

RULE_ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{1,63}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
REASON_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
MAX_LABEL = 64


class InputError(Exception):
    """Lỗi đầu vào: exit 2, không ghi gì. Thông điệp là một mã, không chứa đường dẫn hay dữ liệu."""


# ---------------------------------------------------------------- đọc tệp (cách parse chặt như G7)
def sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: str, limit: int, kind: str) -> bytes:
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
    except OSError as e:
        raise InputError(f"{kind}_KHONG_DOC_DUOC ({type(e).__name__})") from None
    if len(data) > limit:
        raise InputError(f"{kind}_QUA_LON")
    return data


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def _reject_constant(name):
    raise ValueError("non-finite number")


def _parse_float(text):
    v = float(text)
    if v != v or abs(v) == float("inf"):
        raise ValueError("non-finite number")
    return v


def parse_json(data: bytes, kind: str):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
                          parse_float=_parse_float)
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise InputError(f"{kind}_KHONG_PHAI_JSON ({type(e).__name__})") from None


# ---------------------------------------------------------------- kiểm kiểu các trường được đọc
def need(ok, code: str) -> None:
    if not ok:
        raise InputError(code)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_count(v) -> bool:
    return is_int(v) and v >= 0


def label_text(v, code: str) -> str:
    """Nhãn phiên bản: chuỗi 1..64 ký tự, không có ký tự điều khiển."""
    need(isinstance(v, str) and 1 <= len(v) <= MAX_LABEL and not any(ord(c) < 32 or ord(c) == 127 for c in v), code)
    return v


def count_map(v, keys, code: str) -> dict:
    """Từ điển đúng tập khóa `keys`, giá trị là số nguyên không âm. Trả bản dựng lại theo thứ tự `keys`."""
    need(isinstance(v, dict) and set(v) == set(keys) and all(is_count(v[k]) for k in keys), code)
    return {k: v[k] for k in keys}


def enum_list(v, allowed, code: str) -> list:
    need(isinstance(v, list) and all(isinstance(x, str) and x in allowed for x in v), code)
    return list(v)


def label_for(rule_id, index) -> str:
    return rule_id if isinstance(rule_id, str) and RULE_ID_RE.fullmatch(rule_id) else f"RULE_{index}"


def kiem_truy_vet_block(ktv, sha: dict) -> dict:
    need(isinstance(ktv, dict) and ktv.get("schema") == KTV_SCHEMA, "KIEM_TRUY_VET_SAI_SCHEMA")
    shas = ktv.get("sha256")
    need(isinstance(shas, dict), "KIEM_TRUY_VET_SAI_KIEU")
    for key, _ in SHA_KEYS:
        pair = shas.get(key)
        need(isinstance(pair, dict) and isinstance(pair.get("tinh_duoc"), str), "KIEM_TRUY_VET_SAI_KIEU")
        need(pair["tinh_duoc"] == sha[key], "KIEM_TRUY_VET_HASH_LECH")
    need(ktv.get("buoc_da_chay") == STEPS, "KIEM_TRUY_VET_THIEU_BUOC")
    ket_luan, why = ktv.get("ket_luan"), ktv.get("ly_do_khong_dat")
    need(ket_luan in ("DAT", "KHONG_DAT"), "KIEM_TRUY_VET_SAI_KIEU")
    need(isinstance(why, list) and all(isinstance(x, str) and REASON_CODE_RE.fullmatch(x) for x in why),
         "KIEM_TRUY_VET_SAI_KIEU")
    need((ket_luan == "DAT") == (why == []), "KIEM_TRUY_VET_SAI_KIEU")
    script = ktv.get("script")
    need(isinstance(script, dict) and isinstance(script.get("sha256_lf"), str) and SHA_RE.fullmatch(script["sha256_lf"]),
         "KIEM_TRUY_VET_SAI_KIEU")
    return {"ket_luan": ket_luan, "ly_do_khong_dat": list(why), "script_sha256_lf": script["sha256_lf"]}


def report_block(report, sha: dict) -> dict:
    need(isinstance(report, dict) and report.get("schema") == REPORT_SCHEMA, "BAO_CAO_SAI_SCHEMA")
    rf, inp, summary, rules = (report.get(k) for k in ("rules_file", "input", "summary", "rules"))
    need(isinstance(rf, dict) and isinstance(inp, dict) and isinstance(summary, dict) and isinstance(rules, list),
         "BAO_CAO_SAI_KIEU")
    need(rf.get("sha256") == sha["quy_tac"], "BAO_CAO_QUY_TAC_SHA_LECH")
    need(inp.get("input_sha256") == sha["cad_read"], "BAO_CAO_INPUT_SHA_LECH")
    version = label_text(report.get("cadaudit_version"), "BAO_CAO_SAI_KIEU")
    rules_version = label_text(rf.get("rules_version"), "BAO_CAO_SAI_KIEU")
    need(summary.get("overall") in OVERALLS and isinstance(summary.get("all_rules_approved"), bool), "BAO_CAO_SAI_KIEU")
    note = summary.get("overall_note")
    need(note is None or note == OVERALL_NOTE, "BAO_CAO_SAI_KIEU")
    quy_tac = []
    for i, r in enumerate(rules):
        need(isinstance(r, dict), "BAO_CAO_SAI_KIEU")
        need(r.get("rule_status") in RULE_STATUSES and r.get("classification") in CLASSIFICATIONS
             and r.get("verdict") in VERDICTS and isinstance(r.get("coverage_complete"), bool)
             and is_count(r.get("objects_in_scope")), "BAO_CAO_SAI_KIEU")
        quy_tac.append({
            "rule_id": label_for(r.get("rule_id"), i),
            "rule_status": r["rule_status"],
            "classification": r["classification"],
            "verdict": r["verdict"],
            "reasons": enum_list(r.get("reasons"), UNKNOWN_REASONS, "BAO_CAO_SAI_KIEU"),
            "counts": count_map(r.get("counts"), VERDICTS, "BAO_CAO_SAI_KIEU"),
            "objects_in_scope": r["objects_in_scope"],
            "coverage_complete": r["coverage_complete"],
        })
    return {
        "cadaudit_version": version,
        "report_schema": report["schema"],
        "rules_version": rules_version,
        "overall": summary["overall"],
        "all_rules_approved": summary["all_rules_approved"],
        "overall_note": note,
        "rules_by_verdict": count_map(summary.get("rules_by_verdict"), VERDICTS, "BAO_CAO_SAI_KIEU"),
        "rules_by_status": count_map(summary.get("rules_by_status"), RULE_STATUSES, "BAO_CAO_SAI_KIEU"),
        "results_by_verdict": count_map(summary.get("results_by_verdict"), VERDICTS, "BAO_CAO_SAI_KIEU"),
        "quy_tac": quy_tac,
    }


def coverage_block(cad) -> dict:
    """Chỉ `layers` và `xrefs`, chỉ bốn trường có kiểu cố định. `note` (văn bản tự do) không bao giờ được chép."""
    cov = cad.get("coverage") if isinstance(cad, dict) else None
    need(isinstance(cov, dict), "CAD_READ_SAI_KIEU")
    out = {}
    for g in COVERAGE_GROUPS:
        c = cov.get(g)
        need(isinstance(c, dict), "CAD_READ_SAI_KIEU")
        status, expected, enumerated, reason = c.get("status"), c.get("expected"), c.get("enumerated"), c.get("reason")
        need(status in COVERAGE_STATUSES and (expected is None or is_count(expected)) and is_count(enumerated)
             and (reason is None or reason in COVERAGE_REASONS), "CAD_READ_SAI_KIEU")
        out[g] = {"status": status, "expected": expected, "enumerated": enumerated, "reason": reason}
    return out


# ---------------------------------------------------------------- điều phối
def script_hashes(data: bytes) -> dict:
    return {"sha256_tho": sha_hex(data), "sha256_lf": sha_hex(data.replace(b"\r\n", b"\n"))}


def script_info() -> dict:
    return script_hashes(read_bytes(os.path.abspath(__file__), 16 * 1024 * 1024, "SCRIPT"))


def tom_tat(args) -> dict:
    """Kiểm đầu vào rồi dựng bản tóm tắt. Raise InputError khi một điều kiện đầu vào sai (chưa ghi gì)."""
    raw = {"cad_read": read_bytes(args.cad_read, MAX_CAD_READ_BYTES, "CAD_READ"),
           "quy_tac": read_bytes(args.rules, MAX_RULES_BYTES, "QUY_TAC"),
           "bao_cao": read_bytes(args.report, MAX_REPORT_BYTES, "BAO_CAO"),
           "kiem_truy_vet": read_bytes(args.kiem_truy_vet, MAX_KTV_BYTES, "KIEM_TRUY_VET")}
    sha = {k: sha_hex(v) for k, v in raw.items()}
    pinned = {"cad_read": args.sha256_cad_read, "quy_tac": args.sha256_rules, "bao_cao": args.sha256_report}
    for key, code in SHA_KEYS:
        need(sha[key] == pinned[key], code)

    ktv = kiem_truy_vet_block(parse_json(raw["kiem_truy_vet"], "KIEM_TRUY_VET"), sha)
    rep = report_block(parse_json(raw["bao_cao"], "BAO_CAO"), sha)
    cov = coverage_block(parse_json(raw["cad_read"], "CAD_READ"))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    return {
        "schema": OUT_SCHEMA,
        "sha256": {"cad_read": sha["cad_read"], "quy_tac": sha["quy_tac"], "bao_cao": sha["bao_cao"],
                   "kiem_truy_vet": sha["kiem_truy_vet"]},
        "cadaudit_sha": args.cadaudit_sha,
        "cadaudit_version": rep["cadaudit_version"],
        "report_schema": rep["report_schema"],
        "rules_version": rep["rules_version"],
        "overall": rep["overall"],
        "all_rules_approved": rep["all_rules_approved"],
        "overall_note": rep["overall_note"],
        "rules_by_verdict": rep["rules_by_verdict"],
        "rules_by_status": rep["rules_by_status"],
        "results_by_verdict": rep["results_by_verdict"],
        "quy_tac": rep["quy_tac"],
        "coverage": cov,
        "kiem_truy_vet": ktv,
        "script": script_info(),
        "tao_luc": now.isoformat(timespec="seconds"),
    }


def write_new(path: str, out: dict) -> None:
    """Tạo tệp mới (chế độ xb). Tệp, thư mục hay symlink có sẵn đều bị từ chối; không ghi đè, không ghi tệp nào khác."""
    data = (json.dumps(out, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with open(path, "xb") as f:
            f.write(data)
    except FileExistsError:
        raise InputError("OUT_DA_TON_TAI") from None
    except OSError as e:
        raise InputError(f"OUT_KHONG_TAO_DUOC ({type(e).__name__})") from None


def _sha_arg(text: str) -> str:
    v = text.strip().lower()
    if not SHA_RE.fullmatch(v):
        raise argparse.ArgumentTypeError("phai la 64 ky tu hex")
    return v


def _git_sha_arg(text: str) -> str:
    v = text.strip().lower()
    if not GIT_SHA_RE.fullmatch(v):
        raise argparse.ArgumentTypeError("phai la 40 ky tu hex")
    return v


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tom_tat", allow_abbrev=False,
                                description="M04-B: tao ban tom tat de dua vao repo (docs/M04_B_PLAN.md muc 5)")
    for name in ("cad-read", "rules", "report", "kiem-truy-vet", "out"):
        p.add_argument(f"--{name}", required=True)
    for name in ("cad-read", "rules", "report"):
        p.add_argument(f"--sha256-{name}", required=True, type=_sha_arg)
    p.add_argument("--cadaudit-sha", required=True, type=_git_sha_arg)
    return p


def main(argv=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_INPUT
    try:
        if os.path.lexists(args.out):
            raise InputError("OUT_DA_TON_TAI")
        out = tom_tat(args)
        write_new(args.out, out)
    except InputError as e:
        print(f"tom_tat: LOI_DAU_VAO: {e}", file=sys.stderr)
        return EXIT_INPUT
    except Exception as e:  # noqa: BLE001 - lỗi nội bộ không được lẫn với lỗi đầu vào
        print(f"tom_tat: LOI_NOI_BO: {type(e).__name__}", file=sys.stderr)
        return EXIT_INTERNAL
    print(f"tom_tat: da ghi; overall={out['overall']} kiem_truy_vet={out['kiem_truy_vet']['ket_luan']}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
