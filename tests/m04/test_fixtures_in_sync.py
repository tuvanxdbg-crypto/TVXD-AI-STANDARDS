"""The committed fixtures match make_fixtures.py, say they are fake, and contain no CAD file."""
import json
import os
import unittest

import make_fixtures
from m04_helpers import FIX, read_bytes, read_json


class FixturesInSync(unittest.TestCase):
    def test_json_fixtures_match_generator(self):
        for name, doc in make_fixtures.all_fixtures().items():
            with self.subTest(name):
                self.assertEqual(read_json(os.path.join(FIX, name)), json.loads(json.dumps(doc)))

    def test_every_fixture_states_it_is_fake(self):
        for dirpath, _dirs, files in os.walk(FIX):
            for name in files:
                path = os.path.join(dirpath, name)
                text = read_bytes(path).decode("utf-8")
                with self.subTest(os.path.relpath(path, FIX)):
                    if name.endswith(".json"):
                        note = json.loads(text).get("fixture_note", "")
                        self.assertTrue(note.startswith("FIXTURE ONLY"), note)
                    elif name.endswith(".yaml"):
                        self.assertTrue(text.startswith("# FIXTURE ONLY"))
                    else:
                        self.fail(f"unexpected fixture file type: {name}")

    def test_no_cad_files_in_tests_or_package(self):
        bad = []
        for top in (os.path.dirname(FIX), os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(FIX))), "cadaudit")):
            for dirpath, _dirs, files in os.walk(top):
                bad += [os.path.join(dirpath, f) for f in files if f.lower().endswith((".dwg", ".dxf", ".lsp", ".fas", ".vlx"))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
