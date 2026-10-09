# INDEX — M02 fixture library (human-readable)

**FIXTURE ONLY.** Every document, date, applicability entry, reviewer and NotebookLM
mapping here is fake test data for the Standards Gateway tests. Nothing in it describes a
real standard, a real effective date or a real applicability decision.

Machine source of truth: [`INDEX.yaml`](INDEX.yaml) (schema `gateway/schemas/index.v1.json`).
This page is navigation only and is not read by the Gateway. Markdown summaries never
replace the source files.

Source root (configured in `gateway.fixture.json`): [`library/`](library/)

**Contract v2 (M02_NOTEBOOKLM_PRIMARY_TRUSTED_SOURCE).** The Gateway no longer reads `library/` or checks
`sha256`/`sync`. The "Test purpose" column describes the contract-v1 tests. In contract v2 the NotebookLM mapping
column is the query scope (whitelisted notebook + source), and sync identity is optional provenance. Documents without a
NotebookLM source (QCVN-FAKE-01@2019, TCVN-FAKE-9999, IEC-FAKE-60000) are excluded as `NOT_IN_NOTEBOOKLM_SCOPE`.
The library files remain for the local-adapter module tests (`test_gateway_core.LocalAdapter`, Windows controls).

| Document | Versions (effective) | Format / clause scheme | Whitelisted | Applicability (fake) | NotebookLM mapping | Test purpose |
|---|---|---|---|---|---|---|
| QCVN-FAKE-01 | 2024 (2025-01-01 →), 2019 (2020-01-01 → 2025-01-01, superseded) | md / numeric | yes | ELEC-LV-FAKE | 2024 → nb-fixture-001/src-qcvn01-2024, sync matches; 2019 unmapped | exact lookup, version by date, cache |
| QCVN-FAKE-02 | 2023 | md / numeric | **no** | ELEC-LV-FAKE | nb-not-allowed | SOURCE_NOT_ALLOWED |
| LUAT-FAKE-99 | 2025 (2025-07-01 →) | txt / article | yes | all fake work codes | nb-fixture-001/src-luat99, sync matches | Điều/khoản lookup, semantic |
| TCVN-FAKE-7777 | 2023 | md / numeric, Vietnamese file name | yes | LIGHT-FAKE + condition COND-INDOOR | src-tcvn7777, **no sync identity** | Unicode path, conditions, UNKNOWN on missing sync |
| TCVN-FAKE-8888 | 2022 | docx / numeric (table + image) | yes | ELEC-LV-FAKE | src-tcvn8888, **sync hash wrong** | DOCX extraction, layout, drift |
| TCVN-FAKE-9999 | 2021 and 2022, both active | md / numeric | yes | GEN-FAKE | none | VERSION_AMBIGUOUS |
| IEC-FAKE-60000 | 2020 | pdf | yes | ELEC-LV-FAKE | none | UNSUPPORTED_FORMAT |
| HD-FAKE-INJECTION | 2026 | md / numeric | yes | GEN-FAKE | src-injection, sync matches | embedded instructions stay data (canary TVXD-M02-CANARY-5D1E) |
| HD-FAKE-UNREVIEWED | 2026 | md / numeric | yes | **not reviewed** | nb-not-allowed (notebook not whitelisted) | APPLICABILITY_UNKNOWN, notebook whitelist |

Fake work codes: `ELEC-LV-FAKE`, `LIGHT-FAKE`, `GEN-FAKE`. Whitelisted notebook: `nb-fixture-001`.
