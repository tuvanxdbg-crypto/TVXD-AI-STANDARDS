#!/usr/bin/env python3
"""M04-B, điều kiện G7: kiểm truy vết cục bộ (docs/M04_B_PLAN.md mục 5.1).

Chạy ngay sau `python -m cadaudit check`, trên đúng ba tệp đã ghim sha256: tệp CAD_READ, tệp quy tắc YAML và
báo cáo `cadaudit`. Offline, chỉ đọc ba tệp đó, chỉ tạo MỘT tệp mới (`--out`, chế độ `x`, không ghi đè).

Độc lập với `cadaudit`: script KHÔNG import `cadaudit`. Evidence ID được giải bằng bộ giải riêng trong file này
(logic của `resolve_evidence` trong tests/m04/m04_helpers.py, thêm chỉ mục theo handle để chạy nhanh trên bản vẽ
lớn). Kiểm schema dùng `gateway.schema.validate` (gateway/schema.py, bản gốc của M02) với hai schema JSON của
`cadaudit/schemas/`; đây không phải bản sao `cadaudit/_schema.py`, nên không dùng lại chính validator mà
`cadaudit` đã tự kiểm báo cáo. Tên validator được ghi vào output (`schema_validator`).

Các bước (mục 5.1; 2b, 2c, 4b, 4c, 5b, 6b và các kiểm liên kết là bổ sung, xem ghi chú từng hàm):
  1. sha256 ba tệp trùng giá trị truyền vào. Sai thì dừng và vẫn ghi output KHONG_DAT (exit 1).
  2. Báo cáo hợp `cad_audit_report.v1.json` (2b: CAD_READ hợp `cad_read.v1.json`; sai một trong hai thì dừng).
  2c. Bất biến coverage D1 của CAD_READ (`coverage_problems`, viết độc lập theo loader): thiếu mục coverage, hoặc
      enumerated khác số phần tử mảng, hoặc COMPLETE/INCOMPLETE/NOT_EXTRACTED sai điều kiện expected/reason thì
      `CAD_READ_COVERAGE_SAI` và dừng trước bước 3, như khi sai schema.
  3. Mọi evidence ID (cấp quy tắc, cấp dòng, kể cả cấp FILE) đúng dạng, đúng file_id, giải ra ĐÚNG MỘT giá trị.
  4. Mỗi dòng kết quả: `actual` bằng giá trị tại evidence ID của trường được kiểm (xem `verify_row`).
  4b. Tính lại verdict từng dòng INTERNAL_ONLY (reason null) từ giá trị nguồn, bằng phép kiểm hiện thực lại
      độc lập cho cả sáu loại check (`evaluate_check`); lệch thì `DONG_VERDICT_LECH`.
  4c. Metadata từng dòng: `rule_status`, `classification`, `standard_hint` của mỗi dòng bằng tệp quy tắc (phân loại D4
      tính lại) và bằng mục `rules[]` của báo cáo; lệch thì `DONG_METADATA_LECH`.
      UNKNOWN/COVERAGE_INCOMPLETE ở cấp dòng vì "cha thiếu" chỉ hợp lệ khi `parent_unknown` đúng theo selector
      (xem `parent_unknown`); không thì dòng bị kiểm trường và verdict trực tiếp như dòng thường.
  5. Đếm lại PASS/FAIL/UNKNOWN và số dòng theo quy tắc, so với `counts` và `objects_in_scope`.
  5b. Tính lại phạm vi từng quy tắc từ selector (`in_scope`: space, tag, name_pattern, layer, block_name) và so
      tập handle trong phạm vi với tập handle các dòng báo cáo (có tính trùng dòng): thiếu hoặc thừa dòng thì
      `PHAM_VI_LECH`. Nhờ vậy một đối tượng bị bỏ sót hoặc một dòng thừa không lọt qua dù số đếm, verdict và
      phần tổng hợp đã sửa cho tự nhất quán.
  6. Tính lại `coverage_complete`, `verdict`, `reasons` theo D5 từ `coverage` của CAD_READ và các dòng.
  7. Mọi FAIL và UNKNOWN (cấp quy tắc và cấp dòng) có ít nhất một evidence ID.

Output đã lọc: không có tên layer, tên xref, handle, giá trị actual/expected, hay đường dẫn máy. Chỉ có hash, số
đếm, mã lý do và rule_id (rule_id lạ hoặc sai dạng được thay bằng RULE_<số thứ tự>).

Exit: 0 DAT; 1 KHONG_DAT (output vẫn được ghi); 2 lỗi đầu vào hoặc không tạo được output (không ghi gì);
70 lỗi nội bộ (không ghi gì).

  python scripts/m04b/kiem_truy_vet.py --cad-read P --rules P --report P \\
      --sha256-cad-read H --sha256-rules H --sha256-report H --out P [--nguoi-chay T] [--nguoi-duyet T]
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import yaml  # noqa: E402
from gateway import schema as gateway_schema  # noqa: E402  (validator gốc của M02, không phải cadaudit)

OUT_SCHEMA = "tvxd.m04b.kiem_truy_vet/v1"
SCHEMA_VALIDATOR = "gateway.schema.validate (gateway/schema.py, M02; doc lap voi cadaudit, khong dung cadaudit._schema)"
REPORT_SCHEMA_PATH = os.path.join(REPO, "cadaudit", "schemas", "cad_audit_report.v1.json")
CAD_READ_SCHEMA_PATH = os.path.join(REPO, "cadaudit", "schemas", "cad_read.v1.json")

EXIT_DAT, EXIT_KHONG_DAT, EXIT_INPUT, EXIT_INTERNAL = 0, 1, 2, 70
MAX_CAD_READ_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 512 * 1024 * 1024
MAX_RULES_BYTES = 1024 * 1024
MAX_LABEL = 200

GROUPS = ("layers", "blocks", "block_refs", "attributes", "texts", "dimensions", "xrefs", "units")
GROUP_ARRAYS = GROUPS[:-1]                       # units không có handle
NAME_FIELD = {"layers": "name", "blocks": "name", "block_refs": "block_name", "xrefs": "name"}
SELECTOR_KEYS = ("space", "tag", "name_pattern", "layer", "block_name")
CHECK_TYPES = ("name_pattern", "allowed_values", "numeric_range", "required_field", "equals_field", "xref_resolved")
DEFAULT_MAX_LENGTH = 255
PRIMARY_FIELD = {"layers": "name", "blocks": "name", "block_refs": "block_name", "attributes": "tag",
                 "texts": "text_type", "dimensions": "dim_type", "xrefs": "name", "units": "insunits"}
VERDICTS = ("PASS", "FAIL", "UNKNOWN")
UNKNOWN_REASONS = ("COVERAGE_INCOMPLETE", "FIELD_MISSING", "STANDARD_LOOKUP_NOT_ENABLED", "NO_OBJECTS_IN_SCOPE")
STD = "STANDARD_REQUIRED"
INTERNAL = "INTERNAL_ONLY"
SLNE = "STANDARD_LOOKUP_NOT_ENABLED"
COMPLETE = "COMPLETE"
EV_RE = re.compile(r"CADEV:([A-Za-z0-9_-]{1,32}):([0-9A-F]{1,16}|FILE):([A-Za-z0-9_.]{1,64})")
RULE_ID_RE = re.compile(r"[A-Z][A-Z0-9_-]{1,63}")
SHA_RE = re.compile(r"[0-9a-f]{64}")

# Thứ tự cố định của mã lý do KHONG_DAT trong output.
REASON_ORDER = (
    "SHA256_CAD_READ_SAI", "SHA256_QUY_TAC_SAI", "SHA256_BAO_CAO_SAI",
    "BAO_CAO_SAI_SCHEMA", "CAD_READ_SAI_SCHEMA", "CAD_READ_COVERAGE_SAI",
    "LIEN_KET_BAO_CAO_SAI", "QUY_TAC_KHONG_KHOP_TEP",
    "EVIDENCE_ID_SAI_DANG", "EVIDENCE_ID_SAI_FILE_ID", "EVIDENCE_ID_KHONG_GIAI_DUOC", "EVIDENCE_ID_NHIEU_GIA_TRI",
    "DONG_RULE_ID_LA", "DONG_KHONG_TIM_THAY_DOI_TUONG", "DONG_THIEU_ID_TRUONG_KIEM", "ACTUAL_LECH",
    "DONG_VERDICT_LECH", "DONG_LY_DO_LECH", "DONG_METADATA_LECH",
    "PHAM_VI_LECH", "COUNTS_LECH", "OBJECTS_IN_SCOPE_LECH", "COVERAGE_COMPLETE_LECH", "VERDICT_LECH", "REASONS_LECH",
    "SUMMARY_LECH", "FAIL_UNKNOWN_THIEU_EVIDENCE",
)


class InputError(Exception):
    """Lỗi đầu vào hoặc không tạo được output: exit 2, không ghi gì. Thông điệp không chứa đường dẫn."""


# ---------------------------------------------------------------- đọc tệp
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


def load_rules(data: bytes) -> tuple:
    """Đọc quy tắc bằng yaml.safe_load. Trả (rules_version, danh sách quy tắc). Sai cấu trúc là lỗi đầu vào."""
    try:
        doc = yaml.safe_load(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, yaml.YAMLError, RecursionError) as e:
        raise InputError(f"QUY_TAC_KHONG_PHAI_YAML ({type(e).__name__})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        raise InputError("QUY_TAC_SAI_CAU_TRUC")
    rules = []
    for raw in doc["rules"]:
        ok = (isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw.get("applies_to") in GROUPS
              and isinstance(raw.get("check"), dict) and isinstance(raw["check"].get("type"), str)
              and isinstance(raw.get("selector", {}), dict) and isinstance(raw.get("status"), str))
        if not ok:
            raise InputError("QUY_TAC_SAI_CAU_TRUC")
        sel, chk = raw.get("selector", {}), raw["check"]
        if (set(sel) - set(SELECTOR_KEYS) or chk["type"] not in CHECK_TYPES
                or ("name_pattern" in sel and raw["applies_to"] not in NAME_FIELD)):
            raise InputError("QUY_TAC_SAI_CAU_TRUC")
        try:       # biên dịch sẵn; cùng bộ regex `re` của Python như cadaudit
            raw["_sel_regex"] = re.compile(sel["name_pattern"]) if "name_pattern" in sel else None
            raw["_check_regex"] = re.compile(chk["pattern"]) if chk["type"] == "name_pattern" else None
        except (re.error, TypeError, KeyError):
            raise InputError("QUY_TAC_SAI_CAU_TRUC") from None
        rules.append(raw)
    return doc.get("rules_version"), rules


# ---------------------------------------------------------------- bộ giải evidence ID (độc lập với cadaudit)
class Resolver:
    """Giải `CADEV:<file_id>:<handle|FILE>:<trường>` trong tài liệu CAD_READ.

    Logic của `resolve_evidence` (tests/m04/m04_helpers.py): ID không đúng dạng hoặc sai file_id cho danh sách rỗng;
    cấp FILE đi theo đường dẫn chấm trong tài liệu (`units.<trường>` đi vào phần tử đầu của `units`); cấp đối tượng
    lấy trường của MỌI đối tượng cùng handle ở bảy mảng nhóm (trùng handle cho nhiều giá trị). Khác helper: có chỉ
    mục theo handle, và chỉ chấp nhận giá trị đơn (chuỗi, số, bool, null); dict hoặc list không phải một giá trị.
    """

    def __init__(self, doc: dict):
        self.doc = doc
        self.file_id = doc["drawing"]["file_id"]
        self.by_handle = {}          # handle -> các đối tượng (mọi nhóm)
        self.by_group = {}           # (nhóm, handle) -> các đối tượng
        self.attrs_by_parent = {}    # parent_handle -> các attribute (để dòng attribute_tag không quét cả mảng)
        for a in doc.get("attributes", []):
            self.attrs_by_parent.setdefault(a.get("parent_handle"), []).append(a)
        for g in GROUP_ARRAYS:
            for obj in doc.get(g, []):
                if isinstance(obj, dict) and "handle" in obj:
                    self.by_handle.setdefault(obj["handle"], []).append(obj)
                    self.by_group.setdefault((g, obj["handle"]), []).append(obj)

    def values(self, handle: str, field: str) -> list:
        if handle == "FILE":
            parts = field.split(".")
            units = self.doc.get("units")
            node = units[0] if parts[0] == "units" and units else self.doc
            parts = parts[1:] if parts[0] == "units" else parts
            for p in parts:
                if not isinstance(node, dict) or p not in node:
                    return []
                node = node[p]
            return [node]
        return [obj[field] for obj in self.by_handle.get(handle, []) if field in obj]

    def classify(self, ev) -> str:
        """Một trong: sai_dang, sai_file_id, khong_giai_duoc, nhieu_gia_tri, giai_dung_mot."""
        m = EV_RE.fullmatch(ev) if isinstance(ev, str) else None
        if not m:
            return "sai_dang"
        file_id, handle, field = m.groups()
        if file_id != self.file_id:
            return "sai_file_id"
        vals = self.values(handle, field)
        if len(vals) > 1:
            return "nhieu_gia_tri"
        if len(vals) == 0 or isinstance(vals[0], (dict, list)):
            return "khong_giai_duoc"
        return "giai_dung_mot"

    def single(self, ev):
        """(True, giá trị) khi ID giải ra đúng một giá trị đơn, ngược lại (False, None)."""
        if self.classify(ev) != "giai_dung_mot":
            return False, None
        _, handle, field = EV_RE.fullmatch(ev).groups()
        return True, self.values(handle, field)[0]


def coverage_problems(cad: dict) -> int:
    """Số nhóm vi phạm bất biến coverage D1, viết độc lập theo `check_coverage` và vòng kiểm nhóm của
    cadaudit/loader.py (chỉ đọc để đối chiếu). Mỗi nhóm trong GROUPS (kể cả units) phải có mục coverage, và:
      enumerated == số phần tử mảng nhóm (mảng vắng tính là rỗng);
      COMPLETE: expected là số nguyên, expected == enumerated, reason null;
      INCOMPLETE: expected null hoặc enumerated < expected, reason khác null;
      NOT_EXTRACTED: expected null, enumerated == 0, reason khác null."""
    isint = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    bad = 0
    for g in GROUPS:
        c, items = cad["coverage"].get(g), cad.get(g, [])
        if not isinstance(c, dict) or not isinstance(items, list):
            bad += 1
            continue
        status, exp, enum, why = c.get("status"), c.get("expected"), c.get("enumerated"), c.get("reason")
        ok = isint(enum) and enum == len(items)
        if status == COMPLETE:
            ok = ok and isint(exp) and exp == enum and why is None
        elif status == "INCOMPLETE":
            ok = ok and (exp is None or (isint(exp) and enum < exp)) and why is not None
        elif status == "NOT_EXTRACTED":
            ok = ok and exp is None and enum == 0 and why is not None
        else:
            ok = False
        bad += not ok
    return bad


def same(a, b) -> bool:
    """Bằng nhau theo giá trị: số bằng số (không tính bool), còn lại phải cùng kiểu. Không coi True là 1."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if num(a) and num(b):
        return a == b
    return type(a) is type(b) and a == b


# ---------------------------------------------------------------- quy tắc: phân loại, trường kiểm, nhóm đọc
def classify_rule(raw: dict) -> tuple:
    """(classification, classification_reason) theo D4: chỉ nâng lên STANDARD_REQUIRED, không bao giờ hạ."""
    if raw.get("standard_required") is True:
        return STD, "DECLARED"
    src = raw.get("source")
    has_source = isinstance(src, str) and src.strip() != ""
    if raw["applies_to"] == "dimensions" and raw["check"]["type"] == "numeric_range" and not has_source:
        return STD, "UPGRADED_DIMENSION_RANGE_NO_INTERNAL_SOURCE"
    return INTERNAL, "DECLARED"


def reads_groups(raw: dict) -> list:
    """Nhóm quy tắc đọc: applies_to cộng nhóm mà selector hoặc check tham chiếu (D5), theo thứ tự nhóm chuẩn."""
    applies, sel, chk = raw["applies_to"], raw.get("selector", {}), raw["check"]
    reads = {applies}
    if applies in ("block_refs", "attributes") and "block_name" in sel:
        reads.add("blocks")
    if applies == "block_refs" and ("name_pattern" in sel or "block_name" in (chk.get("field"), chk.get("field_a"),
                                                                              chk.get("field_b"))):
        reads.add("blocks")
    if "layer" in sel and applies != "layers":
        reads.add("layers")
        if applies == "attributes":
            reads.add("block_refs")
    if "block_name" in sel and applies == "attributes":
        reads.add("block_refs")
    if chk["type"] == "required_field" and "attribute_tag" in chk:
        reads.add("attributes")
    return [g for g in GROUPS if g in reads]


def checked_fields(raw: dict) -> list:
    """Trường của đối tượng mà phép kiểm đọc (cũng là trường được trỏ bởi evidence của dòng)."""
    chk, t = raw["check"], raw["check"]["type"]
    if t in ("name_pattern", "allowed_values", "numeric_range"):
        return [chk["field"]]
    if t == "required_field":
        return [chk["field"]] if "field" in chk else [PRIMARY_FIELD[raw["applies_to"]]]
    if t == "equals_field":
        return [chk["field_a"], chk["field_b"]]
    return ["path_status"]                       # xref_resolved


# ---------------------------------------------------------------- phép kiểm và selector, hiện thực lại độc lập
def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def evaluate_check(raw: dict, vals: list):
    """Verdict "PASS" hoặc "FAIL" của một đối tượng có mọi trường kiểm khác null; None nếu không tính được
    (kiểu giá trị không hợp phép kiểm). `vals` là giá trị các trường theo thứ tự `checked_fields`.

      name_pattern: độ dài <= max_length (mặc định 255) và fullmatch;  allowed_values: bằng một giá trị cho phép
      (số bằng số, không coi True là 1);  numeric_range: min/max cùng dung sai (mặc định 0);
      required_field (có `field`): không phải chuỗi rỗng sau strip;  equals_field: số thì |a-b| <= tolerance
      (mặc định 0), còn lại bằng nhau;  xref_resolved: path_status là RESOLVED.
    """
    chk, t, v = raw["check"], raw["check"]["type"], vals[0]
    if t == "equals_field":
        a, b = vals
        if _num(a):
            return ("PASS" if abs(a - b) <= chk.get("tolerance", 0) else "FAIL") if _num(b) else None
        return "PASS" if same(a, b) else "FAIL"
    if t == "name_pattern":
        if not isinstance(v, str):
            return None
        ok = len(v) <= chk.get("max_length", DEFAULT_MAX_LENGTH) and raw["_check_regex"].fullmatch(v) is not None
    elif t == "allowed_values":
        ok = any(same(v, x) for x in chk["values"])
    elif t == "numeric_range":
        if not _num(v):
            return None
        tol = chk.get("tolerance", 0)
        ok = ("min" not in chk or v >= chk["min"] - tol) and ("max" not in chk or v <= chk["max"] + tol)
    elif t == "required_field":
        ok = not (isinstance(v, str) and v.strip() == "")
    else:                                         # xref_resolved
        ok = v == "RESOLVED"
    return "PASS" if ok else "FAIL"


def in_scope(rs: "Resolver", raw: dict, obj: dict) -> bool:
    """Đối tượng có nằm trong phạm vi quy tắc không (mọi khóa selector đều phải thỏa).

    space, tag: bằng. name_pattern: fullmatch trên trường tên của nhóm. layer, block_name: của chính đối tượng;
    với nhóm attributes là của block_ref cha, và cha vắng trong dữ liệu thì khóa đó không loại đối tượng."""
    group = raw["applies_to"]
    for key, want in raw.get("selector", {}).items():
        if key in ("space", "tag"):
            ok = obj.get(key) == want
        elif key == "name_pattern":
            name = obj.get(NAME_FIELD[group])
            ok = isinstance(name, str) and raw["_sel_regex"].fullmatch(name) is not None
        else:                                     # layer, block_name
            if group == "attributes":
                parents = rs.by_group.get(("block_refs", obj.get("parent_handle")), [])
                if not parents:
                    continue
                ok = parents[0].get(key) == want
            else:
                ok = obj.get(key) == want
        if not ok:
            return False
    return True


def parent_unknown(rs: "Resolver", raw: dict, obj: dict) -> bool:
    """Theo evaluator `_select`: nhóm attributes, selector có ít nhất một khóa layer hoặc block_name (cần block_ref
    cha), đối tượng thỏa mọi khóa selector khác, và cha không có trong block_refs. Chỉ khi đó dòng mới được là
    UNKNOWN/COVERAGE_INCOMPLETE vì cha thiếu; quy tắc không cần cha thì cha thiếu không đổi gì."""
    sel = raw.get("selector", {})
    if raw["applies_to"] != "attributes" or not ({"layer", "block_name"} & set(sel)):
        return False
    if rs.by_group.get(("block_refs", obj.get("parent_handle"))):
        return False
    return in_scope(rs, raw, obj)


# ---------------------------------------------------------------- bước 4: một dòng kết quả
def verify_row(cad: dict, rs: Resolver, raw: dict, cls: str, row: dict) -> tuple:
    """Trả (tập vấn đề, loại dòng). Vấn đề: khong_tim_thay, thieu_id, actual_lech, verdict_dong_lech, ly_do_lech.

    Trường được kiểm theo loại check (khớp cách evaluator chọn evidence và `actual`):
      name_pattern, allowed_values, numeric_range, required_field có `field`, xref_resolved: một trường
        (`field`, hoặc `path_status` cho xref_resolved); actual là giá trị trường đó.
      equals_field: hai trường; `actual` là giá trị của `field_b` (evidence cả hai trường phải có mặt).
      required_field có `attribute_tag` (INTERNAL_ONLY): trường là `value` của attribute có parent_handle là dòng
        này và tag đúng; không có attribute thì actual phải null, và FAIL chỉ khi `attributes` COMPLETE.
      STANDARD_REQUIRED: actual là giá trị của trường đầu tiên trong danh sách trường kiểm; expected luôn null.
      attributes có parent thiếu (`parent_unknown`): chỉ khi selector có khóa layer/block_name VÀ cha vắng trong
        block_refs VÀ mọi khóa selector khác thỏa. Khi đó dòng phải là UNKNOWN/COVERAGE_INCOMPLETE, actual null,
        evidence là parent_handle và coverage.block_refs.status, và block_refs chưa COMPLETE. Ngược lại (không
        parent_unknown) mà dòng ghi COVERAGE_INCOMPLETE thì dòng bị đánh dấu lệch lý do và vẫn được kiểm trường
        và verdict trực tiếp như dòng thường.
    Thứ tự như evaluator: STANDARD_REQUIRED, parent_unknown, attribute_tag, trường null, check.
    Verdict từng dòng (4b): dòng INTERNAL_ONLY có reason null phải có verdict bằng verdict tính lại từ giá trị
    nguồn bằng `evaluate_check` (required_field/attribute_tag: chuỗi rỗng sau strip là FAIL). Không tính được
    cũng là lệch. Dòng UNKNOWN và dòng STANDARD_REQUIRED không có verdict PASS/FAIL để tính lại; chúng được kiểm
    bằng lý do, trường nguồn null hoặc coverage như trên.
    Mỗi dòng đều kiểm được; không có dòng nào để "không áp dụng".
    """
    probs = set()
    group, chk = raw["applies_to"], raw["check"]
    handle, verdict, reason, actual = row["handle"], row["verdict"], row["reason"], row["actual"]
    cited = set(row["evidence_ids"])
    fid = rs.file_id
    cov = cad.get("coverage", {})

    def status(g):
        return cov.get(g, {}).get("status") if isinstance(cov.get(g), dict) else None

    if group == "units":
        objs = cad["units"][:1] if handle == "FILE" else []
    else:
        objs = rs.by_group.get((group, handle), [])
    if len(objs) != 1:
        return {"khong_tim_thay"}, "khong_tim_thay"
    obj = objs[0]

    def mk(h, f):                                # khớp model.evidence_id: units không có handle
        return f"CADEV:{fid}:FILE:units.{f}" if group == "units" else f"CADEV:{fid}:{h}:{f}"

    def mk_file(path):
        return f"CADEV:{fid}:FILE:{path}"

    def need(ev):
        if ev not in cited:
            probs.add("thieu_id")

    def check_actual(ev, want_null=False):
        ok, v = rs.single(ev)
        if not ok or not same(actual, v) or (want_null and v is not None):
            probs.add("actual_lech")
        return v if ok else None

    # lý do và verdict của dòng phải khớp nhau (UNKNOWN <=> có lý do; SLNE <=> quy tắc STANDARD_REQUIRED)
    if (verdict == "UNKNOWN") == (reason is None) or (cls == STD) != (reason == SLNE):
        probs.add("ly_do_lech")

    if cls == STD:
        fields = checked_fields(raw)
        for f in fields:
            need(mk(handle, f))
        check_actual(mk(handle, fields[0]))
        return probs, "standard_required"

    if parent_unknown(rs, raw, obj):
        if (verdict, reason) != ("UNKNOWN", "COVERAGE_INCOMPLETE") or status("block_refs") == COMPLETE:
            probs.add("ly_do_lech")
        if actual is not None:
            probs.add("actual_lech")
        need(mk(handle, "parent_handle"))
        need(mk_file("coverage.block_refs.status"))
        return probs, "cha_thieu"

    if chk["type"] == "required_field" and "attribute_tag" in chk:
        attrs = [a for a in rs.attrs_by_parent.get(handle, []) if a.get("tag") == chk["attribute_tag"]]
        if attrs:
            ev = f"CADEV:{fid}:{attrs[0]['handle']}:value"
            need(ev)
            ok, v = rs.single(ev)
            if reason == "FIELD_MISSING":
                if not ok or v is not None or actual is not None:
                    probs.add("actual_lech")
            else:
                if reason is not None:
                    probs.add("ly_do_lech")
                if v is None:
                    probs.add("actual_lech")
                check_actual(ev)
                if ok and v is not None:
                    want = ("FAIL" if v.strip() == "" else "PASS") if isinstance(v, str) else None
                    if verdict != want:
                        probs.add("verdict_dong_lech")
            return probs, "attribute_tag"
        complete = status("attributes") == COMPLETE
        if (verdict, reason) != (("FAIL", None) if complete else ("UNKNOWN", "COVERAGE_INCOMPLETE")):
            probs.add("ly_do_lech")
        if actual is not None:
            probs.add("actual_lech")
        need(mk(handle, "block_name"))
        need(mk_file("coverage.attributes.status"))
        if complete:
            need(mk_file("coverage.attributes.enumerated"))
            need(mk_file("coverage.attributes.expected"))
        return probs, "attribute_tag_vang"

    fields = checked_fields(raw)
    for f in fields:
        need(mk(handle, f))
    resolved = [rs.single(mk(handle, f)) for f in fields]
    if not all(ok for ok, _ in resolved):
        probs.add("actual_lech")
    null_any = any(ok and v is None for ok, v in resolved)
    if reason == "FIELD_MISSING":
        if actual is not None or not null_any:
            probs.add("actual_lech")
    else:
        if reason is not None:           # lý do không hợp lệ cho dòng này (kể cả COVERAGE_INCOMPLETE khi cha không thiếu)
            probs.add("ly_do_lech")
        if null_any:
            probs.add("actual_lech")
        check_actual(mk(handle, fields[-1]))      # equals_field: actual là field_b
        if all(ok for ok, _ in resolved) and not null_any and verdict != evaluate_check(raw, [v for _, v in resolved]):
            probs.add("verdict_dong_lech")
    return probs, "truong_kiem"


# ---------------------------------------------------------------- các bước kiểm
def step_links(cad, rules_doc_version, report, sha) -> dict:
    inp, rf = report["input"], report["rules_file"]
    return {
        "file_id": inp["file_id"] == cad["drawing"]["file_id"],
        "input_sha256": inp["input_sha256"] == sha["cad_read"],
        "dwg_sha256": inp["dwg_sha256"] == cad["drawing"]["sha256"],
        "rules_sha256": rf["sha256"] == sha["quy_tac"],
        "rules_version": rf["rules_version"] == rules_doc_version,
    }


def step3(report, rs: Resolver) -> dict:
    c = {"tong": 0, "giai_dung_mot": 0, "khong_giai_duoc": 0, "nhieu_gia_tri": 0, "sai_dang": 0, "sai_file_id": 0,
         "tong_cap_quy_tac": 0, "tong_cap_dong": 0}
    for level, items in (("tong_cap_quy_tac", report["rules"]), ("tong_cap_dong", report["results"])):
        for item in items:
            for ev in item["evidence_ids"]:
                c["tong"] += 1
                c[level] += 1
                c[rs.classify(ev)] += 1
    return c


def label_for(rule_id, index) -> str:
    return rule_id if isinstance(rule_id, str) and RULE_ID_RE.fullmatch(rule_id) else f"RULE_{index}"


def step456(cad, rs: Resolver, raw_rules: list, report: dict) -> tuple:
    """Bước 4, 5, 6, 7 và bổ sung (khớp metadata quy tắc, tổng hợp). Trả (khối output, tập mã lý do)."""
    reasons = set()
    cov = cad["coverage"]
    by_id = {}
    for r in raw_rules:
        by_id.setdefault(r["id"], r)
    expected_ids = [r["id"] for r in raw_rules]
    reported_ids = [r["rule_id"] for r in report["rules"]]
    if expected_ids != reported_ids:
        reasons.add("QUY_TAC_KHONG_KHOP_TEP")

    # --- bước 4
    rows_by_rule, c4 = {}, {"so_dong": len(report["results"]), "dong_da_kiem": 0, "actual_khop": 0, "actual_lech": 0,
                            "thieu_id_truong_kiem": 0, "khong_tim_thay_doi_tuong": 0, "verdict_dong_lech": 0,
                            "ly_do_lech": 0, "meta_dong_lech": 0,
                            "rule_id_la": 0, "theo_loai": {}}
    classes = {rid: classify_rule(raw)[0] for rid, raw in by_id.items()}
    rep_by_id = {}
    for r in report["rules"]:
        rep_by_id.setdefault(r["rule_id"], r)
    for row in report["results"]:
        rid = row["rule_id"]
        if rid not in by_id:
            c4["rule_id_la"] += 1
            continue
        rows_by_rule.setdefault(rid, []).append(row)
        probs, kind = verify_row(cad, rs, by_id[rid], classes[rid], row)
        raw_rule, rep_rule = by_id[rid], rep_by_id.get(rid)
        want_meta = (raw_rule["status"], classes[rid], raw_rule.get("standard_hint"))
        if (row["rule_status"], row["classification"], row["standard_hint"]) != want_meta or (
                rep_rule is not None and (row["rule_status"], row["classification"], row["standard_hint"]) != (
                    rep_rule["rule_status"], rep_rule["classification"], rep_rule["standard_hint"])):
            probs.add("meta_dong_lech")
        c4["dong_da_kiem"] += 1
        c4["theo_loai"][kind] = c4["theo_loai"].get(kind, 0) + 1
        if "actual_lech" in probs:
            c4["actual_lech"] += 1
        else:
            c4["actual_khop"] += 1
        c4["thieu_id_truong_kiem"] += "thieu_id" in probs
        c4["khong_tim_thay_doi_tuong"] += "khong_tim_thay" in probs
        c4["verdict_dong_lech"] += "verdict_dong_lech" in probs
        c4["ly_do_lech"] += "ly_do_lech" in probs
        c4["meta_dong_lech"] += "meta_dong_lech" in probs
    for key, code in (("rule_id_la", "DONG_RULE_ID_LA"), ("khong_tim_thay_doi_tuong", "DONG_KHONG_TIM_THAY_DOI_TUONG"),
                      ("thieu_id_truong_kiem", "DONG_THIEU_ID_TRUONG_KIEM"), ("actual_lech", "ACTUAL_LECH"),
                      ("verdict_dong_lech", "DONG_VERDICT_LECH"), ("ly_do_lech", "DONG_LY_DO_LECH"),
                      ("meta_dong_lech", "DONG_METADATA_LECH")):
        if c4[key]:
            reasons.add(code)

    # --- bước 5, 6 theo từng quy tắc của báo cáo
    per_rule = []
    for i, rep in enumerate(report["rules"]):
        rid = rep["rule_id"]
        raw = by_id.get(rid)
        entry = {"rule_id": label_for(rid, i)}
        rows = rows_by_rule.get(rid, [])
        counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
        if raw is None:
            entry.update({"co_trong_tep_quy_tac": False, "so_muc_lech": None})
            per_rule.append(entry)
            reasons.add("QUY_TAC_KHONG_KHOP_TEP")
            continue
        cls, cls_reason = classify_rule(raw)
        reads = reads_groups(raw)
        meta_ok = (rep["rule_status"] == raw["status"] and rep["classification"] == cls
                   and rep["classification_reason"] == cls_reason and rep["applies_to"] == raw["applies_to"]
                   and rep["reads_groups"] == reads and rep["standard_hint"] == raw.get("standard_hint"))
        incomplete = [g for g in reads if (cov.get(g) or {}).get("status") != COMPLETE]
        coverage_complete = not incomplete
        if cls == STD:
            verdict, why = "UNKNOWN", [SLNE]
        elif counts["FAIL"]:
            verdict, why = "FAIL", []
        elif incomplete:
            verdict, why = "UNKNOWN", ["COVERAGE_INCOMPLETE"]
        elif not rows:
            verdict, why = "UNKNOWN", ["NO_OBJECTS_IN_SCOPE"]
        elif counts["UNKNOWN"]:
            found = {r["reason"] for r in rows if r["verdict"] == "UNKNOWN"}
            verdict, why = "UNKNOWN", [x for x in UNKNOWN_REASONS if x in found]
        else:
            verdict, why = "PASS", []
        group = raw["applies_to"]
        scope = collections.Counter(o.get("handle", "FILE") for o in cad.get(group, []) if in_scope(rs, raw, o))
        got = collections.Counter(r["handle"] for r in rows)
        thieu, thua = sum((scope - got).values()), sum((got - scope).values())
        flags = {
            "pham_vi_khop": thieu == 0 and thua == 0,
            "counts_khop": rep["counts"] == counts,
            "objects_in_scope_khop": rep["objects_in_scope"] == len(rows),
            "coverage_complete_khop": rep["coverage_complete"] == coverage_complete,
            "verdict_khop": rep["verdict"] == verdict,
            "reasons_khop": rep["reasons"] == why,
            "meta_khop": meta_ok,
        }
        so_lech = (sum(1 for v in VERDICTS if rep["counts"][v] != counts[v]) + sum(
            1 for k in ("pham_vi_khop", "objects_in_scope_khop", "coverage_complete_khop", "verdict_khop", "reasons_khop",
                        "meta_khop")
            if not flags[k]))
        entry.update(flags)
        entry.update({"thieu_dong": thieu, "thua_dong": thua, "so_doi_tuong_pham_vi_tinh_lai": sum(scope.values())})
        entry.update({"so_muc_lech": so_lech, "verdict": rep["verdict"], "verdict_tinh_lai": verdict,
                      "reasons": list(rep["reasons"]), "reasons_tinh_lai": why,
                      "coverage_complete": rep["coverage_complete"], "coverage_complete_tinh_lai": coverage_complete,
                      "so_dong_tinh_lai": len(rows), "counts_tinh_lai": counts})
        for key, code in (("pham_vi_khop", "PHAM_VI_LECH"), ("counts_khop", "COUNTS_LECH"), ("objects_in_scope_khop", "OBJECTS_IN_SCOPE_LECH"),
                          ("coverage_complete_khop", "COVERAGE_COMPLETE_LECH"), ("verdict_khop", "VERDICT_LECH"),
                          ("reasons_khop", "REASONS_LECH"), ("meta_khop", "QUY_TAC_KHONG_KHOP_TEP")):
            if not flags[key]:
                reasons.add(code)
        per_rule.append(entry)

    # --- bước 7: mọi FAIL và UNKNOWN có ít nhất một evidence ID
    thieu_q = sum(1 for x in report["rules"] if x["verdict"] in ("FAIL", "UNKNOWN") and not x["evidence_ids"])
    thieu_d = sum(1 for x in report["results"] if x["verdict"] in ("FAIL", "UNKNOWN") and not x["evidence_ids"])
    c7 = {"quy_tac_thieu_evidence": thieu_q, "dong_thieu_evidence": thieu_d}
    if thieu_q or thieu_d:
        reasons.add("FAIL_UNKNOWN_THIEU_EVIDENCE")

    # --- bổ sung: phần tổng hợp của báo cáo tính lại từ chính danh sách quy tắc và dòng
    by_rule = {v: sum(1 for x in report["rules"] if x["verdict"] == v) for v in VERDICTS}
    by_result = {v: sum(1 for x in report["results"] if x["verdict"] == v) for v in VERDICTS}
    by_status = {s: sum(1 for x in report["rules"] if x["rule_status"] == s) for s in ("FIXTURE", "PROPOSED", "APPROVED")}
    overall = "HAS_FAIL" if by_rule["FAIL"] else "HAS_UNKNOWN" if by_rule["UNKNOWN"] else "ALL_RULES_PASS"
    approved = bool(report["rules"]) and by_status["APPROVED"] == len(report["rules"])
    s = report["summary"]
    summary_ok = (s["rules_by_verdict"] == by_rule and s["results_by_verdict"] == by_result
                  and s["rules_by_status"] == by_status and s["overall"] == overall
                  and s["all_rules_approved"] == approved
                  and s.get("overall_note") == ("RULES_NOT_APPROVED" if overall == "ALL_RULES_PASS" and not approved else None))
    if not summary_ok:
        reasons.add("SUMMARY_LECH")
    block = {"buoc4_actual": c4, "buoc5_6_quy_tac": per_rule, "buoc7_thieu_evidence": c7,
             "tong_hop_khop": summary_ok}
    return block, reasons


# ---------------------------------------------------------------- điều phối
def sha_pair(computed: str, pinned: str) -> dict:
    return {"tinh_duoc": computed, "ghim": pinned, "khop": computed == pinned}


def script_info() -> dict:
    data = read_bytes(os.path.abspath(__file__), 16 * 1024 * 1024, "SCRIPT")
    return {"sha256_tho": sha_hex(data), "sha256_lf": sha_hex(data.replace(b"\r\n", b"\n")),
            "schema_validator": SCHEMA_VALIDATOR}


def kiem(args) -> dict:
    """Chạy các bước, trả dict output (chưa có ket_luan cuối). Raise InputError khi đầu vào không dùng được."""
    raw = {"cad_read": read_bytes(args.cad_read, MAX_CAD_READ_BYTES, "CAD_READ"),
           "quy_tac": read_bytes(args.rules, MAX_RULES_BYTES, "QUY_TAC"),
           "bao_cao": read_bytes(args.report, MAX_REPORT_BYTES, "BAO_CAO")}
    pinned = {"cad_read": args.sha256_cad_read, "quy_tac": args.sha256_rules, "bao_cao": args.sha256_report}
    sha = {k: sha_hex(v) for k, v in raw.items()}
    out = {"schema": OUT_SCHEMA, "ket_luan": None, "ly_do_khong_dat": [], "script": script_info(),
           "sha256": {k: sha_pair(sha[k], pinned[k]) for k in raw},
           "buoc2_schema": None, "lien_ket_bao_cao": None, "buoc3_evidence_id": None, "buoc4_actual": None,
           "buoc5_6_quy_tac": None, "buoc7_thieu_evidence": None, "tong_hop_khop": None,
           "buoc_da_chay": ["1"], "nguoi_chay": args.nguoi_chay, "nguoi_duyet": args.nguoi_duyet, "chay_luc": None}
    reasons = set()
    for key, code in (("cad_read", "SHA256_CAD_READ_SAI"), ("quy_tac", "SHA256_QUY_TAC_SAI"),
                      ("bao_cao", "SHA256_BAO_CAO_SAI")):
        if sha[key] != pinned[key]:
            reasons.add(code)
    if reasons:                                   # bước 1: sai hash thì dừng
        return finish(out, reasons)

    cad = parse_json(raw["cad_read"], "CAD_READ")
    report = parse_json(raw["bao_cao"], "BAO_CAO")
    rules_version, raw_rules = load_rules(raw["quy_tac"])
    schemas = {}
    for key, path in (("bao_cao", REPORT_SCHEMA_PATH), ("cad_read", CAD_READ_SCHEMA_PATH)):
        data = read_bytes(path, 16 * 1024 * 1024, "SCHEMA")
        schemas[key] = (parse_json(data, "SCHEMA"), sha_hex(data))
    problems = {"bao_cao": gateway_schema.validate(report, schemas["bao_cao"][0]),
                "cad_read": gateway_schema.validate(cad, schemas["cad_read"][0])}
    out["buoc_da_chay"].append("2")
    out["buoc2_schema"] = {
        "schema_validator": SCHEMA_VALIDATOR,
        "bao_cao": {"hop_le": not problems["bao_cao"], "so_loi": len(problems["bao_cao"]), "schema_sha256": schemas["bao_cao"][1]},
        "cad_read": {"hop_le": not problems["cad_read"], "so_loi": len(problems["cad_read"]), "schema_sha256": schemas["cad_read"][1],
                     "so_nhom_coverage_sai": None},
    }
    if problems["bao_cao"]:
        reasons.add("BAO_CAO_SAI_SCHEMA")
    if problems["cad_read"]:
        reasons.add("CAD_READ_SAI_SCHEMA")
    else:                                         # bất biến coverage cần cấu trúc đúng schema
        out["buoc2_schema"]["cad_read"]["so_nhom_coverage_sai"] = coverage_problems(cad)
        if out["buoc2_schema"]["cad_read"]["so_nhom_coverage_sai"]:
            reasons.add("CAD_READ_COVERAGE_SAI")
    if reasons:                                   # cấu trúc không đáng tin thì không đi tiếp
        return finish(out, reasons)

    rs = Resolver(cad)
    links = step_links(cad, rules_version, report, sha)
    out["lien_ket_bao_cao"] = links
    if not all(links.values()):
        reasons.add("LIEN_KET_BAO_CAO_SAI")
    c3 = step3(report, rs)
    out["buoc3_evidence_id"] = c3
    for key, code in (("sai_dang", "EVIDENCE_ID_SAI_DANG"), ("sai_file_id", "EVIDENCE_ID_SAI_FILE_ID"),
                      ("khong_giai_duoc", "EVIDENCE_ID_KHONG_GIAI_DUOC"), ("nhieu_gia_tri", "EVIDENCE_ID_NHIEU_GIA_TRI")):
        if c3[key]:
            reasons.add(code)
    block, more = step456(cad, rs, raw_rules, report)
    out.update(block)
    out["buoc_da_chay"] += ["3", "4", "5", "6", "7"]
    return finish(out, reasons | more)


def finish(out: dict, reasons: set) -> dict:
    out["ly_do_khong_dat"] = [r for r in REASON_ORDER if r in reasons]
    out["ket_luan"] = "KHONG_DAT" if reasons else "DAT"
    out["chay_luc"] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat(timespec="seconds")
    return out


def write_new(path: str, out: dict) -> None:
    """Tạo tệp mới (chế độ x). Tệp, thư mục hay symlink có sẵn đều bị từ chối; không ghi đè, không ghi tệp nào khác."""
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


def _label_arg(text: str) -> str:
    if len(text) > MAX_LABEL or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise argparse.ArgumentTypeError(f"toi da {MAX_LABEL} ky tu, khong co ky tu dieu khien")
    return text


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kiem_truy_vet", allow_abbrev=False,
                                description="M04-B G7: kiem truy vet cuc bo (docs/M04_B_PLAN.md muc 5.1)")
    for name in ("cad-read", "rules", "report", "out"):
        p.add_argument(f"--{name}", required=True)
    for name in ("cad-read", "rules", "report"):
        p.add_argument(f"--sha256-{name}", required=True, type=_sha_arg)
    p.add_argument("--nguoi-chay", type=_label_arg, default=None)
    p.add_argument("--nguoi-duyet", type=_label_arg, default=None)
    return p


def main(argv=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_INPUT
    try:
        if os.path.lexists(args.out):
            raise InputError("OUT_DA_TON_TAI")
        out = kiem(args)
        write_new(args.out, out)
    except InputError as e:
        print(f"kiem_truy_vet: LOI_DAU_VAO: {e}", file=sys.stderr)
        return EXIT_INPUT
    except Exception as e:  # noqa: BLE001 - lỗi nội bộ không được lẫn với KHONG_DAT (exit 1)
        print(f"kiem_truy_vet: LOI_NOI_BO: {type(e).__name__}", file=sys.stderr)
        return EXIT_INTERNAL
    print(f"kiem_truy_vet: ket_luan={out['ket_luan']}" + (" ly_do=" + ",".join(out["ly_do_khong_dat"]) if out["ly_do_khong_dat"] else ""))
    return EXIT_DAT if out["ket_luan"] == "DAT" else EXIT_KHONG_DAT


if __name__ == "__main__":
    sys.exit(main())
