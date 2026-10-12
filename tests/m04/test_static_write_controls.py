"""D6 layer 3: the AST allow-list scan is clean on every .py file of cadaudit/, and each rule catches its sample.

The scan is an additional layer; it does not replace the run-time controls tested in test_writer_guards.py.
"""
import os
import textwrap
import unittest

import ast_rules
from ast_rules import scan_file, scan_source
from m04_helpers import REPO

PACKAGE = os.path.join(REPO, "cadaudit")


def rules_of(source, is_writer=False):
    return {v.rule for v in scan_source(textwrap.dedent(source), is_writer)}


class PackageIsClean(unittest.TestCase):
    def test_every_py_file_in_cadaudit_is_clean(self):
        files = []
        for dirpath, _dirs, names in os.walk(PACKAGE):
            files += [os.path.join(dirpath, n) for n in names if n.endswith(".py")]
        self.assertGreaterEqual(len(files), 10)
        self.assertIn(os.path.join(PACKAGE, "_report_writer.py"), files)
        for path in sorted(files):
            is_writer = os.path.basename(path) == "_report_writer.py"
            with self.subTest(os.path.relpath(path, REPO)):
                self.assertEqual(scan_file(path, is_writer), [])

    def test_the_writer_is_not_clean_as_an_ordinary_module(self):
        # it really is the only module that writes: scanned without the writer allow-list it must be flagged
        self.assertTrue(scan_file(os.path.join(PACKAGE, "_report_writer.py"), False))

    def test_no_other_module_names_os_open_or_the_write_calls(self):
        for name in os.listdir(PACKAGE):
            if name.endswith(".py") and name != "_report_writer.py":
                with open(os.path.join(PACKAGE, name), "rb") as f:
                    text = f.read().decode("utf-8")
                for needle in ("os.open", "os.replace", "os.rename", "os.unlink", "os.link", "os.write", "os.fdopen", ".write(", ".write_text("):
                    with self.subTest(module=name, needle=needle):
                        self.assertNotIn(needle, text)


class NegativeSamples(unittest.TestCase):
    """Every sample of docs/M04_CAD_AUDIT_READONLY.md D6 layer 3, plus one per rule."""

    def assert_flagged(self, source, rule, is_writer=False):
        self.assertIn(rule, rules_of(source, is_writer), source)

    def test_spec_samples(self):
        cases = [
            ("Path(...).write_text", 'Path("x").write_text("a")', "BANNED_ATTR"),
            ("Path import", "from pathlib import Path\nPath('x').write_text('a')", "IMPORT_BANNED"),
            ("p.open('w')", 'p.open("w")', "OPEN_MODE"),
            ("os.open", "import os\nos.open('x', 0)", "OS_ATTR"),
            ("os.replace", "import os\nos.replace('a', 'b')", "BANNED_ATTR"),
            ("os.rename", "import os\nos.rename('a', 'b')", "BANNED_ATTR"),
            ("os.unlink", "import os\nos.unlink('a')", "BANNED_ATTR"),
            ("f.write outside the writer", "f.write('x')", "BANNED_ATTR"),
            ("import os as o + o.remove", "import os as o\no.remove('a')", "IMPORT_ALIAS"),
            ("o.remove is also flagged by name", "import os as o\no.remove('a')", "BANNED_ATTR"),
            ("from os import remove", "from os import remove", "FROM_IMPORT_NAME"),
            ("__import__", '__import__("os")', "DYNAMIC"),
            ("importlib.import_module", "import importlib\nimportlib.import_module('os')", "IMPORT_BANNED"),
            ("getattr(os, 'remove')", "import os\ngetattr(os, 'remove')", "GETATTR"),
            ("getattr(os, name)", "import os\nname = 'remove'\ngetattr(os, name)", "GETATTR"),
            ("eval", "eval('1')", "DYNAMIC"),
            ("exec", "exec('x = 1')", "DYNAMIC"),
            ("subprocess", "import subprocess", "IMPORT_BANNED"),
            ("ctypes", "import ctypes", "IMPORT_BANNED"),
            ("win32com", "import win32com.client", "IMPORT_BANNED"),
            ("socket", "import socket", "IMPORT_BANNED"),
            ("yaml.load", "import yaml\nyaml.load('a: 1')", "YAML"),
        ]
        for label, source, rule in cases:
            with self.subTest(label):
                self.assert_flagged(source, rule)

    def test_every_banned_module(self):
        for mod in ("subprocess", "socket", "ctypes", "win32com", "comtypes", "pythoncom", "importlib", "shutil",
                    "pathlib", "io", "tempfile"):
            with self.subTest(mod):
                self.assert_flagged(f"import {mod}", "IMPORT_BANNED")
                self.assert_flagged(f"from {mod} import x", "IMPORT_BANNED")

    def test_modules_outside_the_allow_list(self):
        for src in ("import urllib.request", "import random", "import http.client", "from collections import deque",
                    "import json, os, shutil", "import os.path, glob", "import pickle"):
            with self.subTest(src):
                self.assertTrue(rules_of(src) & {"IMPORT_NOT_ALLOWED", "IMPORT_BANNED"})

    def test_alias_rules(self):
        for src in ("import os as o", "import yaml as y", "import os.path as p", "from os import path as p", "from yaml import safe_load as s"):
            with self.subTest(src):
                self.assert_flagged(src, "IMPORT_ALIAS")
        self.assertEqual(rules_of("import datetime as dt\nimport hashlib"), set())     # alias is only banned for os and yaml

    def test_from_os_names_are_an_allow_list(self):
        for src in ("from os import remove", "from os import *", "from os import open", "from os import path, replace",
                    "from yaml import load", "from yaml import *", "from yaml import unsafe_load"):
            with self.subTest(src):
                self.assert_flagged(src, "FROM_IMPORT_NAME")
        self.assertEqual(rules_of("from os import path\nfrom yaml import safe_load"), set())

    def test_every_banned_attribute_whatever_the_object(self):
        for attr in sorted(ast_rules.BANNED_ATTRS | ast_rules.BANNED_ATTRS_EXTRA):
            with self.subTest(attr):
                self.assert_flagged(f"anything.{attr}(1)", "BANNED_ATTR")
                self.assert_flagged(f"x = thing.{attr}", "BANNED_ATTR")          # access without a call
                self.assert_flagged(f"getattr(thing, {attr!r})", "GETATTR")

    def test_os_attribute_allow_list_outside_the_writer(self):
        for attr in ("open", "system", "fdopen", "popen", "walk", "listdir", "scandir", "environ", "getcwd", "chdir"):
            with self.subTest(attr):
                self.assert_flagged(f"import os\nos.{attr}", "OS_ATTR")
        self.assertEqual(rules_of("import os\nos.path.join('a', 'b')\nos.fspath('a')\nos.name\nos.sep"), set())
        self.assert_flagged("import os\nx = os", "BARE_MODULE")
        self.assert_flagged("import os\nf(os)", "BARE_MODULE")

    def test_open_only_with_a_literal_read_mode(self):
        for src in ("open(p)", "open(p, 'w')", "open(p, 'wb')", "open(p, 'a')", "open(p, 'r+')", "open(p, 'rb+')",
                    "open(p, mode)", "open(p, mode=m)", "open(p, 'w' if x else 'r')", "x.open('rb')", "x.open()",
                    "f = open", "g(open)", "open(p, mode='w')"):
            with self.subTest(src):
                self.assert_flagged(src, "OPEN_MODE")
        for src in ("open(p, 'r')", "open(p, 'rb')", "open(p, mode='rb')", "open(p, 'r', encoding='utf-8')"):
            with self.subTest(src):
                self.assertEqual(rules_of(src), set())

    def test_dynamic_access(self):
        for src in ("__import__('os')", "eval('1')", "exec('1')", "compile('1', 'f', 'exec')", "globals()", "vars(x)",
                    "setattr(x, 'a', 1)", "delattr(x, 'a')", "x.__dict__", "__builtins__", "x.__builtins__",
                    "x.__globals__", "x.__subclasses__()"):
            with self.subTest(src):
                self.assert_flagged(src, "DYNAMIC")
        self.assertEqual(rules_of("import re\nre.compile('a')"), set())               # re.compile is not the builtin

    def test_getattr_only_with_a_literal_allowed_name(self):
        for src in ("getattr(x, name)", "getattr(x)", "getattr(x, 'remove')", "getattr(x, 'open')", "getattr(x, '__dict__')",
                    "getattr(x, 'eval')", "getattr(x, 'a' + 'b')", "getattr(x, f'{n}')"):
            with self.subTest(src):
                self.assert_flagged(src, "GETATTR")
        for src in ("getattr(x, 'name')", "getattr(x, 'name', None)", "import os\ngetattr(os, 'path')"):
            with self.subTest(src):
                self.assertEqual(rules_of(src), set())

    def test_yaml_only_safe_load(self):
        for src in ("yaml.load(s)", "yaml.unsafe_load(s)", "yaml.full_load(s)", "yaml.load_all(s)", "yaml.dump(x)",
                    "yaml.safe_load(s, Loader=yaml.Loader)", "yaml.safe_load(s, Loader=L)", "load(s, Loader=L)"):
            with self.subTest(src):
                self.assert_flagged("import yaml\n" + src, "YAML")
        self.assertEqual(rules_of("import yaml\nyaml.safe_load(s)\nyaml.YAMLError"), set())
        self.assert_flagged("import yaml\ny = yaml", "BARE_MODULE")

    def test_autocad_string(self):
        for src in ("x = 'AutoCAD.Application'", "x = 'autocad.application.24'", "x = f'AutoCAD.Application {y}'"):
            with self.subTest(src):
                self.assert_flagged(src, "STRING")

    def test_clean_read_only_code_passes(self):
        src = """
            import json
            import os
            import yaml
            from functools import lru_cache

            def read(path):
                with open(os.path.join(os.path.dirname(path), "x.json"), "rb") as f:
                    return json.loads(f.read().decode("utf-8"))

            def parse(data):
                return yaml.safe_load(data)

            def pick(obj):
                return getattr(obj, "name", None)
        """
        self.assertEqual(rules_of(src), set())


class WriterAllowList(unittest.TestCase):
    """Inside _report_writer.py only the enumerated attributes and calls are allowed."""

    def test_the_enumerated_set_is_exactly_what_the_spec_needs(self):
        needed = {"os.open", "os.write", "os.fsync", "os.close", "os.link", "os.unlink", "os.rename", "os.lstat",
                  "secrets.token_hex", "hashlib.sha256", "os.path.realpath", "os.path.abspath", "os.path.samefile"}
        self.assertTrue(needed <= ast_rules.WRITER_DOTTED)
        for banned in ("os.replace", "os.remove", "os.chmod", "os.mkdir", "os.makedirs", "os.rmdir", "os.symlink",
                       "os.truncate", "os.ftruncate", "os.utime", "os.fdopen", "os.system", "os.popen"):
            self.assertNotIn(banned, ast_rules.WRITER_DOTTED)

    def test_writer_flags_everything_outside_the_set(self):
        cases = [
            ("os.replace", "import os\nos.replace('a', 'b')", "WRITER_ATTR"),
            ("os.remove", "import os\nos.remove('a')", "WRITER_ATTR"),
            ("os.chmod", "import os\nos.chmod('a', 0)", "WRITER_ATTR"),
            ("os.mkdir", "import os\nos.mkdir('a')", "WRITER_ATTR"),
            ("os.makedirs", "import os\nos.makedirs('a')", "WRITER_ATTR"),
            ("os.symlink", "import os\nos.symlink('a', 'b')", "WRITER_ATTR"),
            ("os.truncate", "import os\nos.truncate('a', 0)", "WRITER_ATTR"),
            ("os.fdopen", "import os\nos.fdopen(1)", "WRITER_ATTR"),
            ("os.system", "import os\nos.system('x')", "WRITER_ATTR"),
            ("open()", "open('a', 'wb')", "WRITER_CALL"),
            ("file object write", "f.write(b'x')", "WRITER_CALL"),
            ("write_text", "p.write_text('x')", "WRITER_CALL"),
            ("unlisted builtin", "print('x')", "WRITER_CALL"),
            ("unlisted method", "x.append(1)", "WRITER_CALL"),
            ("another module", "import sys\nsys.exit(1)", "WRITER_ATTR"),
            ("json in the writer", "import json\njson.dumps({})", "WRITER_ATTR"),
            ("shutil", "import shutil\nshutil.copy('a', 'b')", "IMPORT_BANNED"),
            ("indirect call", "fns[0]('a')", "WRITER_CALL"),
            ("getattr with banned name", "import os\ngetattr(os, 'replace')", "GETATTR"),
            ("getattr with variable", "import os\ngetattr(os, n)", "GETATTR"),
            ("dynamic import", "__import__('os')", "DYNAMIC"),
        ]
        for label, source, rule in cases:
            with self.subTest(label):
                self.assertIn(rule, rules_of(source, is_writer=True), source)

    def test_writer_accepts_its_own_primitives(self):
        src = """
            import hashlib
            import os
            import secrets
            import stat

            def f(parent, name, data):
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(os.path.join(parent, name), flags, 0o644)
                os.write(fd, data)
                os.fsync(fd)
                os.close(fd)
                os.link(name, name + "x", follow_symlinks=False)
                os.unlink(name)
                os.rename(name, name)
                return hashlib.sha256(data).hexdigest(), secrets.token_hex(16), stat.S_ISREG(os.lstat(name).st_mode)
        """
        self.assertEqual(rules_of(src, is_writer=True), set())


if __name__ == "__main__":
    unittest.main()
