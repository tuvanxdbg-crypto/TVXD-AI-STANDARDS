"""D6 layer 3: static write controls for cadaudit/, by allow-list, using the ast module.

scan_source(source, is_writer) returns a list of Violation(rule, line, detail). An empty list means clean.
This layer is additional; it does not replace the run-time checks of cadaudit/_report_writer.py (layer 2).

Outside _report_writer.py:
  - imports only from ALLOWED_MODULES, never BANNED_MODULES, no alias on os/yaml; every name taken from a module
    (`import m` then `m.x`, or `from m import x`) must be in MODULE_ATTRS[m] (os and os.path included);
  - relative imports (`from . import x`, `from .m import x`) bind names too: from the package root only RELATIVE_ROOT_NAMES,
    from _report_writer only RELATIVE_WRITER_NAMES, from any other module nothing named like a stdlib module;
  - no attribute or call named in BANNED_ATTRS (whatever the object), no attribute ACCESS named in BANNED_ACCESS
    (open, os, _os, sys, _sys, modules, FileType, ...), a module name is never used as a bare value;
  - no subscript with a module name as the key (`x["shutil"]`, `sys.modules["os"]`), and `sys.modules` itself is banned;
  - open() only with a literal "r" or "rb" mode, at most two positional arguments, no `opener=` and no `**kwargs`.
Inside _report_writer.py: only the enumerated attribute chains (explicit os.O_* flags too), calls and getattr names in
WRITER_* below.
Everywhere: no __import__/eval/exec/compile/globals/vars/setattr/delattr/__dict__/__builtins__, getattr only with a
literal, allowed attribute name, yaml only safe_load (plus YAML_EXTRA_BY_FILE), no Loader= keyword, no `opener=`
keyword, no "AutoCAD.Application" string.
"""
import ast
import os
from collections import namedtuple

Violation = namedtuple("Violation", "rule line detail")

ALLOWED_MODULES = {"json", "re", "hashlib", "argparse", "os", "os.path", "stat", "errno", "sys", "secrets",
                   "datetime", "dataclasses", "typing", "functools", "yaml"}
BANNED_MODULES = {"subprocess", "socket", "ctypes", "win32com", "comtypes", "pythoncom", "importlib", "shutil",
                  "pathlib", "io", "tempfile"}
NO_ALIAS_ROOTS = {"os", "yaml"}
# Outside the writer a module's attributes (or `from m import x` names) are an explicit allow-list: re-exports such as
# argparse._os, os.path.os, sys.modules or argparse.FileType are therefore not reachable. Only what the package uses.
MODULE_ATTRS = {
    "os": {"path", "fspath", "name", "sep"},
    "os.path": {"abspath", "basename", "dirname", "join", "realpath", "normcase", "splitext", "commonpath"},
    "sys": {"exit", "stderr"},
    "argparse": {"ArgumentParser"},
    "json": {"loads", "dumps"},
    "re": {"compile", "error", "fullmatch", "match", "search", "sub"},
    "hashlib": {"sha256"},
    "datetime": {"date", "datetime", "timedelta", "timezone"},
    "yaml": {"safe_load", "YAMLError"},
    "dataclasses": {"dataclass", "field"},
    "functools": {"lru_cache"},
    "typing": {"Any", "Callable", "Iterable", "Mapping", "Optional", "Sequence", "Union"},
    "secrets": {"token_hex"},
    "stat": {"S_ISDIR", "S_ISLNK", "S_ISREG", "FILE_ATTRIBUTE_REPARSE_POINT"},
    "errno": set(),
}
# Extra names per file (by base name): rules.py composes the YAML node graph with the safe loader class to reject
# duplicate mapping keys before yaml.safe_load. Nothing else may touch yaml.SafeLoader.
YAML_EXTRA_BY_FILE = {"rules.py": {"SafeLoader", "MappingNode", "SequenceNode", "ScalarNode"}}
# Relative imports. Package root: only these. _report_writer: only the entry points the CLI calls (check_target only
# reads the file system; write_report is the writer). Other package modules: any name that is not a stdlib module name.
RELATIVE_ROOT_NAMES = {"__version__", "_schema"}
RELATIVE_WRITER_NAMES = {"write_report", "check_target"}

BANNED_ATTRS = {"write", "write_text", "write_bytes", "writelines", "truncate", "unlink", "remove", "rename",
                "replace", "link", "symlink", "rmdir", "mkdir", "makedirs", "chmod", "chown", "utime"}
# Not in the spec list; same family, caught whatever the object is (e.g. path.os.system).
BANNED_ATTRS_EXTRA = {"system", "fdopen", "popen", "startfile", "execv", "execl", "spawnl", "spawnv", "kill",
                      "ftruncate", "fchmod", "fchown", "lchmod", "lchown", "removedirs", "renames", "mkfifo",
                      "mknod", "sendfile", "pwrite", "posix_spawn", "copy_file_range"}
BANNED_NAMES = {"__import__", "eval", "exec", "compile", "globals", "vars", "setattr", "delattr", "__builtins__"}
BANNED_DYNAMIC_ATTRS = {"__dict__", "__builtins__", "__globals__", "__subclasses__", "__getattribute__"}
# Attribute ACCESS (not only calls) with these names is banned: they reach another module's `os`/`sys` or the opener.
BANNED_ACCESS = {"os", "_os", "sys", "_sys", "modules", "FileType", "open", "builtins", "io", "genericpath",
                 "posixpath", "ntpath"}
GETATTR_FORBIDDEN = BANNED_ATTRS | BANNED_ATTRS_EXTRA | BANNED_NAMES | BANNED_DYNAMIC_ATTRS | BANNED_ACCESS
OS_ATTRS_OUTSIDE_WRITER = MODULE_ATTRS["os"]
FORBIDDEN_STRING = "autocad.application"
STDLIB_NAMES = ALLOWED_MODULES | BANNED_MODULES | {"builtins", "posixpath", "ntpath", "genericpath", "_io", "nt", "posix"}

# What _report_writer.py may use: exactly what D6 layer 2 needs.
WRITER_MODULE_ROOTS = {"os", "hashlib", "secrets", "stat"}
WRITER_DOTTED = {
    "os.path", "os.name",
    "os.path.abspath", "os.path.realpath", "os.path.dirname", "os.path.basename", "os.path.join",
    "os.path.normcase", "os.path.splitext", "os.path.commonpath", "os.path.samefile",
    "os.open", "os.write", "os.read", "os.fsync", "os.close", "os.fstat", "os.lstat", "os.link", "os.unlink",
    "os.rename", "os.O_RDONLY", "os.O_WRONLY", "os.O_CREAT", "os.O_EXCL",     # explicit: no os.O_TRUNC, O_RDWR, O_APPEND
    "hashlib.sha256", "secrets.token_hex",
    "stat.S_ISLNK", "stat.S_ISDIR", "stat.S_ISREG", "stat.FILE_ATTRIBUTE_REPARSE_POINT",
}
WRITER_NAME_CALLS = {"len", "getattr", "isinstance", "memoryview", "any", "ord", "type",
                     "_fail", "_same_path", "_inside", "check_target", "_write_all", "_remove_own_tmp", "_verify", "_close_quietly",
                     "CadAuditError", "OSError"}
WRITER_METHOD_CALLS = {"lower", "upper", "rstrip", "startswith", "update", "hexdigest"}
# getattr in the writer may only fetch these (no getattr(os, "O_TRUNC", 0) around the explicit flag list).
WRITER_GETATTR_NAMES = {"O_NOFOLLOW", "O_BINARY", "O_CLOEXEC", "O_DIRECTORY", "st_file_attributes"}


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


assert ALLOWED_MODULES <= set(MODULE_ATTRS), "every allowed module needs an explicit attribute allow-list"


def scan_source(source: str, is_writer: bool = False, filename: str = "") -> list:
    """filename is the base name of the scanned file; it only selects YAML_EXTRA_BY_FILE."""
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out: list = []

    def add(rule, node, detail):
        out.append(Violation(rule, getattr(node, "lineno", 0), detail))

    def allowed(mod):
        base = MODULE_ATTRS.get(mod, set())
        return base | YAML_EXTRA_BY_FILE.get(filename, set()) if mod == "yaml" else base

    module_names = set()    # every local name bound to a module by an import statement
    bound = {}              # local name -> dotted module path, for modules that have an attribute allow-list
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                local, path = (a.asname, a.name) if a.asname else (root, root)
                module_names.add(local)
                if path in MODULE_ATTRS:
                    bound[local] = path
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mod = node.module or ""
            for a in node.names:
                full = f"{mod}.{a.name}"
                if full in MODULE_ATTRS and a.name in allowed(mod):      # from os import path -> os.path
                    module_names.add(a.asname or a.name)
                    bound[a.asname or a.name] = full

    def mod_of(expr):
        """Dotted module path that a Name / Attribute expression denotes, or None."""
        if isinstance(expr, ast.Name):
            return bound.get(expr.id)
        if isinstance(expr, ast.Attribute):
            base = mod_of(expr.value)
            if base is not None and expr.attr in allowed(base) and f"{base}.{expr.attr}" in MODULE_ATTRS:
                return f"{base}.{expr.attr}"
        return None

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
                    if a.name == "*":
                        add("FROM_IMPORT_NAME", node, f"from {mod} import *")
                    elif mod in MODULE_ATTRS and a.name not in allowed(mod):
                        add("FROM_IMPORT_NAME", node, f"from {mod} import {a.name}")
            else:
                dots = "." * node.level
                mod = node.module
                if node.level > 1 or (mod is not None and "." in mod):
                    add("IMPORT_NOT_ALLOWED", node, f"from {dots}{mod or ''} import ... (only the cadaudit package itself)")
                for a in node.names:
                    where = f"from {dots}{mod or ''} import {a.name}"
                    if a.name == "*":
                        add("FROM_IMPORT_NAME", node, where)
                    elif mod is None:
                        if a.name not in RELATIVE_ROOT_NAMES:
                            add("FROM_IMPORT_NAME", node, where)
                    elif mod == "_report_writer":
                        if a.name not in RELATIVE_WRITER_NAMES:
                            add("FROM_IMPORT_NAME", node, where + " (only the writer's entry points)")
                    elif a.name in STDLIB_NAMES or a.name in GETATTR_FORBIDDEN:
                        add("FROM_IMPORT_NAME", node, where + " (a stdlib module or banned name re-exported)")
        # ---- dynamic access and strings (everywhere)
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES:
                add("DYNAMIC", node, node.id)
            parent = parents.get(node)
            if node.id in bound and isinstance(node.ctx, ast.Load):
                ok = isinstance(parent, ast.Attribute) and parent.value is node
                if (not ok and isinstance(parent, ast.Call) and _chain(parent.func) == "getattr"
                        and parent.args and parent.args[0] is node):
                    ok = True  # getattr(<module>, "<literal>") is judged by the getattr rule
                if not ok:
                    add("BARE_MODULE", node, f"{node.id} used as a value")
            if node.id == "open" and not (isinstance(parent, ast.Call) and parent.func is node):
                add("OPEN_MODE", node, "open referenced without being called")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if FORBIDDEN_STRING in node.value.lower():
                add("STRING", node, "AutoCAD.Application")
            parent = parents.get(node)
            if (isinstance(parent, ast.Subscript) and parent.slice is node
                    and node.value in BANNED_MODULES | {"os", "sys", "builtins", "posix", "nt", "_io"}):
                add("MODULE_SUBSCRIPT", node, f"[{node.value!r}]: looking a module up by name (sys.modules-style) is banned")
        elif isinstance(node, ast.keyword):
            if node.arg == "Loader":
                add("YAML", node.value, "Loader= argument")
            elif node.arg == "opener":
                add("OPENER", node.value, "opener= argument (a custom opener bypasses the mode check)")

        if isinstance(node, ast.Attribute):
            if node.attr in BANNED_DYNAMIC_ATTRS:
                add("DYNAMIC", node, node.attr)
            if node.attr in BANNED_ACCESS and not (is_writer and node.attr == "open"):
                add("BANNED_ATTR", node, f".{node.attr} (access to this attribute name is banned)")
            chain = _chain(node)
            root = chain.split(".")[0] if chain else None
            base = mod_of(node.value)
            if base is not None and node.attr not in allowed(base) and (not is_writer or base == "yaml"):
                if base in ("os", "os.path"):
                    add("OS_ATTR", node, f"{base}.{node.attr}" + (" (os.open/os.system/os.fdopen are banned)"
                                                                if node.attr in ("open", "system", "fdopen") else ""))
                elif base == "yaml":
                    add("YAML", node, f"yaml.{node.attr} (only yaml.safe_load is allowed)")
                else:
                    add("MODULE_ATTR", node, f"{base}.{node.attr} is not in the allow-list for {base}")
            if is_writer:
                if root in module_names and root not in WRITER_MODULE_ROOTS and root != "yaml":
                    add("WRITER_ATTR", node, f"{chain} (module not allowed in the writer)")
                elif root in WRITER_MODULE_ROOTS and root in module_names:
                    parent = parents.get(node)
                    outermost = not (isinstance(parent, ast.Attribute) and parent.value is node)
                    if outermost and chain not in WRITER_DOTTED:
                        add("WRITER_ATTR", node, f"{chain} is not in the writer's allowed set")
            elif node.attr in BANNED_ATTRS or node.attr in BANNED_ATTRS_EXTRA:
                add("BANNED_ATTR", node, node.attr)

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
                    if (len(node.args) > 2 or any(isinstance(a, ast.Starred) for a in node.args)
                            or any(k.arg is None for k in node.keywords)):
                        add("OPEN_MODE", node, "open() takes (path, mode) only: no extra positional, *args or **kwargs")
            elif isinstance(f, ast.Attribute) and f.attr == "open" and not is_writer:
                add("OPEN_MODE", node, f"{_chain(f) or '<expr>.open'}() is not allowed (only open(path, 'r'|'rb'))")
            if isinstance(f, ast.Name) and f.id == "getattr":
                name_arg = node.args[1] if len(node.args) > 1 else None
                if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
                    add("GETATTR", node, "getattr needs a literal attribute name")
                elif name_arg.value in GETATTR_FORBIDDEN:
                    add("GETATTR", node, f"getattr(..., {name_arg.value!r}) names a banned attribute")
                elif is_writer and name_arg.value not in WRITER_GETATTR_NAMES:
                    add("GETATTR", node, f"getattr(..., {name_arg.value!r}) is not in the writer's allowed names")
                elif (not is_writer and node.args and mod_of(node.args[0]) is not None and name_arg.value not in allowed(mod_of(node.args[0]))):
                    add("GETATTR", node, f"getattr({mod_of(node.args[0])}, {name_arg.value!r}) is not in the module's allow-list")
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
        return scan_source(f.read().decode("utf-8"), is_writer, os.path.basename(path))
