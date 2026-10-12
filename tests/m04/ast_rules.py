"""D6 layer 3: static write controls for cadaudit/, by allow-list, using the ast module.

scan_source(source, is_writer) returns a list of Violation(rule, line, detail). An empty list means clean.
This layer is additional; it does not replace the run-time checks of cadaudit/_report_writer.py (layer 2).

Outside _report_writer.py:
  - imports only from ALLOWED_MODULES, never BANNED_MODULES, no alias on os/yaml, `from os import` only ALLOWED_FROM;
  - no attribute or call named in BANNED_ATTRS (whatever the object), no os.open/os.system/os.fdopen,
    only os.<name> in OS_ATTRS_OUTSIDE_WRITER;
  - open() (or .open()) only with a literal "r" or "rb" mode.
Inside _report_writer.py: only the enumerated attribute chains and calls in WRITER_* below.
Everywhere: no __import__/eval/exec/compile/globals/vars/setattr/delattr/__dict__/__builtins__, getattr only with a
literal, allowed attribute name, yaml only safe_load, no Loader= keyword, no "AutoCAD.Application" string.
"""
import ast
from collections import namedtuple

Violation = namedtuple("Violation", "rule line detail")

ALLOWED_MODULES = {"json", "re", "hashlib", "argparse", "os", "os.path", "stat", "errno", "sys", "secrets",
                   "datetime", "dataclasses", "typing", "functools", "yaml"}
BANNED_MODULES = {"subprocess", "socket", "ctypes", "win32com", "comtypes", "pythoncom", "importlib", "shutil",
                  "pathlib", "io", "tempfile"}
NO_ALIAS_ROOTS = {"os", "yaml"}
ALLOWED_FROM = {"os": {"path", "fspath"}, "yaml": {"safe_load", "YAMLError"}}

BANNED_ATTRS = {"write", "write_text", "write_bytes", "writelines", "truncate", "unlink", "remove", "rename",
                "replace", "link", "symlink", "rmdir", "mkdir", "makedirs", "chmod", "chown", "utime"}
# Not in the spec list; same family, caught whatever the object is (e.g. path.os.system).
BANNED_ATTRS_EXTRA = {"system", "fdopen", "popen", "startfile", "execv", "execl", "spawnl", "spawnv", "kill",
                      "ftruncate", "fchmod", "fchown", "lchmod", "lchown", "removedirs", "renames", "mkfifo",
                      "mknod", "sendfile", "pwrite", "posix_spawn", "copy_file_range"}
BANNED_NAMES = {"__import__", "eval", "exec", "compile", "globals", "vars", "setattr", "delattr", "__builtins__"}
BANNED_DYNAMIC_ATTRS = {"__dict__", "__builtins__", "__globals__", "__subclasses__", "__getattribute__"}
GETATTR_FORBIDDEN = BANNED_ATTRS | BANNED_ATTRS_EXTRA | BANNED_NAMES | BANNED_DYNAMIC_ATTRS | {"open"}
OS_ATTRS_OUTSIDE_WRITER = {"path", "fspath", "name", "sep"}
YAML_ATTRS = {"safe_load", "YAMLError"}
FORBIDDEN_STRING = "autocad.application"

# What _report_writer.py may use: exactly what D6 layer 2 needs.
WRITER_MODULE_ROOTS = {"os", "hashlib", "secrets", "stat"}
WRITER_DOTTED = {
    "os.path", "os.name",
    "os.path.abspath", "os.path.realpath", "os.path.dirname", "os.path.basename", "os.path.join",
    "os.path.normcase", "os.path.splitext", "os.path.commonpath", "os.path.samefile",
    "os.open", "os.write", "os.read", "os.fsync", "os.close", "os.fstat", "os.lstat", "os.link", "os.unlink",
    "os.rename", "os.O_RDONLY", "os.O_WRONLY", "os.O_CREAT", "os.O_EXCL",
    "hashlib.sha256", "secrets.token_hex",
    "stat.S_ISLNK", "stat.S_ISDIR", "stat.S_ISREG", "stat.FILE_ATTRIBUTE_REPARSE_POINT",
}
WRITER_NAME_CALLS = {"len", "getattr", "isinstance", "memoryview", "any", "ord", "type",
                     "_fail", "_same_path", "_inside", "check_target", "_write_all", "_remove_own_tmp", "_verify", "_close_quietly",
                     "CadAuditError", "OSError"}
WRITER_METHOD_CALLS = {"lower", "upper", "rstrip", "startswith", "update", "hexdigest"}


def _chain(node):
    """Dotted name of a Name/Attribute chain ('os.path.join'), or None when the chain does not start at a Name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def scan_source(source: str, is_writer: bool = False) -> list:
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out: list = []

    def add(rule, node, detail):
        out.append(Violation(rule, getattr(node, "lineno", 0), detail))

    module_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                module_names.add(a.asname or a.name.split(".")[0])

    for node in ast.walk(tree):
        # ---- imports
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root in BANNED_MODULES:
                    add("IMPORT_BANNED", node, a.name)
                elif a.name not in ALLOWED_MODULES:
                    add("IMPORT_NOT_ALLOWED", node, a.name)
                if a.asname and root in NO_ALIAS_ROOTS:
                    add("IMPORT_ALIAS", node, f"{a.name} as {a.asname}")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                mod = node.module or ""
                root = mod.split(".")[0]
                if root in BANNED_MODULES:
                    add("IMPORT_BANNED", node, mod)
                elif mod not in ALLOWED_MODULES:
                    add("IMPORT_NOT_ALLOWED", node, mod)
                for a in node.names:
                    if root in NO_ALIAS_ROOTS and a.asname:
                        add("IMPORT_ALIAS", node, f"from {mod} import {a.name} as {a.asname}")
                    if a.name == "*" and root in ALLOWED_FROM:
                        add("FROM_IMPORT_NAME", node, f"from {mod} import *")
                    elif mod in ALLOWED_FROM and a.name not in ALLOWED_FROM[mod]:
                        add("FROM_IMPORT_NAME", node, f"from {mod} import {a.name}")
        # ---- dynamic access and strings (everywhere)
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES:
                add("DYNAMIC", node, node.id)
            parent = parents.get(node)
            if node.id in ("os", "yaml") and node.id in module_names:
                ok = isinstance(parent, ast.Attribute) and parent.value is node
                if (not ok and node.id == "os" and isinstance(parent, ast.Call) and _chain(parent.func) == "getattr"
                        and parent.args and parent.args[0] is node):
                    ok = True  # getattr(os, "<literal>") is judged by the getattr rule
                if not ok:
                    add("BARE_MODULE", node, f"{node.id} used as a value")
            if node.id == "open" and not (isinstance(parent, ast.Call) and parent.func is node):
                add("OPEN_MODE", node, "open referenced without being called")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if FORBIDDEN_STRING in node.value.lower():
                add("STRING", node, "AutoCAD.Application")
        elif isinstance(node, ast.keyword):
            if node.arg == "Loader":
                add("YAML", node.value, "Loader= argument")

        if isinstance(node, ast.Attribute):
            if node.attr in BANNED_DYNAMIC_ATTRS:
                add("DYNAMIC", node, node.attr)
            chain = _chain(node)
            root = chain.split(".")[0] if chain else None
            if root == "yaml" and "yaml" in module_names and isinstance(node.value, ast.Name) and node.attr not in YAML_ATTRS:
                add("YAML", node, f"yaml.{node.attr} (only yaml.safe_load is allowed)")
            if is_writer:
                if root in module_names and root not in WRITER_MODULE_ROOTS and root != "yaml":
                    add("WRITER_ATTR", node, f"{chain} (module not allowed in the writer)")
                elif root in WRITER_MODULE_ROOTS and root in module_names:
                    parent = parents.get(node)
                    outermost = not (isinstance(parent, ast.Attribute) and parent.value is node)
                    if outermost and not (chain in WRITER_DOTTED or (root == "os" and chain.startswith("os.O_"))):
                        add("WRITER_ATTR", node, f"{chain} is not in the writer's allowed set")
            else:
                if node.attr in BANNED_ATTRS or node.attr in BANNED_ATTRS_EXTRA:
                    add("BANNED_ATTR", node, node.attr)
                if (isinstance(node.value, ast.Name) and node.value.id == "os" and "os" in module_names
                        and node.attr not in OS_ATTRS_OUTSIDE_WRITER):
                    add("OS_ATTR", node, f"os.{node.attr}" + (" (os.open/os.system/os.fdopen are banned)"
                                                            if node.attr in ("open", "system", "fdopen") else ""))

        # ---- calls
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "open":
                if is_writer:
                    add("WRITER_CALL", node, "open()")
                else:
                    mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                    if not (isinstance(mode, ast.Constant) and mode.value in ("r", "rb")):
                        add("OPEN_MODE", node, "open() needs a literal 'r' or 'rb' mode")
            elif isinstance(f, ast.Attribute) and f.attr == "open" and not is_writer:
                add("OPEN_MODE", node, f"{_chain(f) or '<expr>.open'}() is not allowed (only open(path, 'r'|'rb'))")
            if isinstance(f, ast.Name) and f.id == "getattr":
                name_arg = node.args[1] if len(node.args) > 1 else None
                if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
                    add("GETATTR", node, "getattr needs a literal attribute name")
                elif name_arg.value in GETATTR_FORBIDDEN:
                    add("GETATTR", node, f"getattr(..., {name_arg.value!r}) names a banned attribute")
            if is_writer:
                if isinstance(f, ast.Name):
                    if f.id not in WRITER_NAME_CALLS:
                        add("WRITER_CALL", node, f"{f.id}() is not in the writer's allowed calls")
                elif isinstance(f, ast.Attribute):
                    chain = _chain(f)
                    if chain is not None and chain.split(".")[0] in module_names:
                        pass  # judged as an attribute chain above
                    elif f.attr not in WRITER_METHOD_CALLS:
                        add("WRITER_CALL", node, f".{f.attr}() is not in the writer's allowed calls")
                else:
                    add("WRITER_CALL", node, "indirect call")
    return out


def scan_file(path: str, is_writer: bool) -> list:
    with open(path, "rb") as f:
        return scan_source(f.read().decode("utf-8"), is_writer)
