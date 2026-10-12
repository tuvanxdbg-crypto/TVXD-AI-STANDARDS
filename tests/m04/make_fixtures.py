#!/usr/bin/env python3
"""Generate the FAKE CAD_READ fixtures under tests/m04/fixtures/ (D7). Not a CAD tool: it only builds dictionaries.

Every fixture states it is fake in `fixture_note`. No fixture comes from a real drawing, a CHUAN-HOA-CAD dump or
a DWG file. tests/m04/test_fixtures_in_sync.py checks that the committed files match this script.

  python tests/m04/make_fixtures.py            # rewrite tests/m04/fixtures/*.json
"""
import copy
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures")
NOTE = "FIXTURE ONLY: fake extraction data for M04-A tests. Not from a real drawing; no DWG exists."
FAKE_DWG_SHA = hashlib.sha256(b"FAKE FIXTURE BYTES - NOT A DRAWING - F01").hexdigest()


def complete(n):
    return {"status": "COMPLETE", "expected": n, "enumerated": n, "reason": None}


def layer(h, name):
    return {"handle": h, "space": "MODEL", "name": name, "color": 7, "linetype": "Continuous", "lineweight": 25,
            "plot": True, "frozen": False, "off": False, "locked": False}


def text(h, font, height, value="GHI CHU", layer_name="A-ANNO-TEXT"):
    return {"handle": h, "space": "MODEL", "text_type": "TEXT", "value": value, "style": "STD", "font": font,
            "height": height, "layer": layer_name}


def base():
    layers = [layer("10", "A-WALL"), layer("11", "A-DOOR"), layer("12", "A-ANNO-TEXT"), layer("13", "A-ANNO-DIM")]
    blocks = [
        {"handle": "20", "space": "MODEL", "name": "DOOR-900", "is_xref_dependent": False, "entity_count": 12},
        {"handle": "21", "space": "MODEL", "name": "TITLEBLOCK", "is_xref_dependent": False, "entity_count": 30},
    ]

    def ref(h, block, layer_name, x):
        return {"handle": h, "space": "MODEL", "block_name": block, "layer": layer_name, "insert_x": x,
                "insert_y": 0.0, "insert_z": 0.0, "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0, "rotation": 0.0}

    block_refs = [ref("30", "DOOR-900", "A-DOOR", 1000.0), ref("31", "TITLEBLOCK", "A-ANNO-TEXT", 0.0)]
    attributes = [
        {"handle": "40", "space": "MODEL", "parent_handle": "31", "tag": "DRAWING_NO", "value": "FX-001"},
        {"handle": "41", "space": "MODEL", "parent_handle": "31", "tag": "REVISION", "value": "A"},
    ]
    texts = [text("50", "arial.ttf", 2.5), text("51", "arial.ttf", 3.5, "KICH THUOC")]
    dimensions = [{"handle": "60", "space": "MODEL", "dim_type": "LINEAR", "measured_value": 2400.0,
                   "display_value": 2400.0, "dimscale": 1.0, "layer": "A-ANNO-DIM"}]
    xrefs = [{"handle": "70", "space": "MODEL", "name": "XR-SITE", "path_status": "RESOLVED"}]
    units = [{"insunits": 4, "measurement": 1}]
    return {
        "schema": "tvxd.cadaudit.cad_read/v1",
        "fixture_note": NOTE,
        "drawing": {"file_id": "F01", "file_name": "FIXTURE-SAMPLE-01.dwg", "sha256": FAKE_DWG_SHA,
                    "size_bytes": 4096, "source_tool": "FIXTURE-GENERATOR", "source_tool_version": "0",
                    "extracted_at": "2026-10-12T10:00:00+07:00", "read_mode": "READ_ONLY", "dwg_modified": False},
        "coverage": {"layers": complete(4), "blocks": complete(2), "block_refs": complete(2),
                     "attributes": complete(2), "texts": complete(2), "dimensions": complete(1),
                     "xrefs": complete(1), "units": complete(1)},
        "layers": layers, "blocks": blocks, "block_refs": block_refs, "attributes": attributes, "texts": texts,
        "dimensions": dimensions, "xrefs": xrefs, "units": units,
    }


def make_fail():
    d = base()
    d["layers"].append(layer("14", "wall_01"))                      # wrong layer name
    d["coverage"]["layers"] = complete(5)
    d["texts"] = [text("50", "comic.ttf", 2.5),                      # wrong font
                  text("51", "arial.ttf", 1.0, "KICH THUOC")]         # wrong height
    d["attributes"] = [d["attributes"][1]]                           # DRAWING_NO missing on the title block
    d["coverage"]["attributes"] = complete(1)
    d["dimensions"][0]["display_value"] = 2500.0                     # display value overridden
    d["xrefs"][0]["path_status"] = "NOT_FOUND"                       # xref not found
    return d


def make_unknown():
    d = base()
    d["coverage"]["layers"] = {"status": "INCOMPLETE", "expected": 5, "enumerated": 4, "reason": "READ_ERROR",
                               "note": "fake: one layer record unreadable"}
    d["attributes"] = [d["attributes"][1]]
    d["coverage"]["attributes"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 1,
                                   "reason": "XREF_DEPENDENT"}
    d["texts"][0]["font"] = None                                      # field that could not be read
    d["dimensions"] = []
    d["coverage"]["dimensions"] = {"status": "NOT_EXTRACTED", "expected": None, "enumerated": 0,
                                   "reason": "NOT_REQUESTED"}
    d["xrefs"][0]["path_status"] = "NOT_FOUND"
    d["coverage"]["xrefs"] = {"status": "INCOMPLETE", "expected": None, "enumerated": 1,
                              "reason": "XREF_DEPENDENT"}
    return d


def make_errors():
    bad_schema = base()
    bad_schema["layers"][0]["unexpected_field"] = 1
    rw = base()
    rw["drawing"]["read_mode"] = "READ_WRITE"
    dup = base()
    dup["texts"][0]["handle"] = "10"                                  # same handle as a layer
    cov = base()
    cov["coverage"]["layers"] = {"status": "COMPLETE", "expected": 5, "enumerated": 4, "reason": None}
    dangling = base()
    dangling["attributes"][0]["parent_handle"] = "FF"                 # block_refs is COMPLETE
    return {"error_bad_schema.json": bad_schema, "error_read_mode_read_write.json": rw,
            "error_duplicate_handle.json": dup, "error_coverage_inconsistent.json": cov,
            "error_dangling_reference.json": dangling}


def all_fixtures():
    out = {"cad_read_pass.json": base(), "cad_read_fail.json": make_fail(), "cad_read_unknown.json": make_unknown()}
    out.update(make_errors())
    return out


def dump(doc) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, doc in all_fixtures().items():
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(dump(copy.deepcopy(doc)))
        print("wrote", name)


if __name__ == "__main__":
    main()
