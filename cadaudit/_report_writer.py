"""The ONLY module of cadaudit that writes to disk (D6 layer 2). Fail-closed.

Invariant: cadaudit never opens an existing file for writing and never truncates, replaces, renames or deletes an
existing file, except the temporary file it has just created itself. Every write is an exclusive create, so even if
a path is swapped for a link, the tool can only add one new file, never alter an existing drawing.

Windows has no dir_fd, so there a parent directory swapped between the check and the write could make the report land
elsewhere (the invariant above still holds). A killed process may leave a `.cadaudit-tmp-*` file; the tool never
deletes anything at start-up and a temporary file is never a report.
"""
import hashlib
import os
import secrets
import stat

from .errors import CadAuditError

TMP_PREFIX = ".cadaudit-tmp-"
_WIN_RESERVED = ("CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                 "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9")
_WIN_BAD_CHARS = '<>:"|?*'


def _fail(code: str, message: str):
    raise CadAuditError(code, message, exit_code=3)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _inside(child: str, folder: str) -> bool:
    """True when child equals folder or lies below it (compared after normalisation, case-insensitive on Windows)."""
    c, d = os.path.normcase(os.path.abspath(child)), os.path.normcase(os.path.abspath(folder))
    try:
        return os.path.commonpath([c, d]) == d
    except ValueError:  # different drives
        return False


def check_target(out_path, input_path, rules_path) -> tuple:
    """Validate --out before anything is created. Returns (parent_dir, file_name, parent_id) where parent_id is the
    (st_dev, st_ino) of the parent as seen by lstat here; write_report compares it with the directory it opens.
    Raises OUT_* errors."""
    if not isinstance(out_path, str) or not out_path or "\x00" in out_path:
        _fail("OUT_INVALID", "--out must be a non-empty path")
    out_abs = os.path.abspath(out_path)
    parent, name = os.path.dirname(out_abs), os.path.basename(out_abs)
    raw_name = os.path.basename(out_path)   # as typed: Windows path normalisation drops trailing dots and spaces
    if not name or not raw_name:
        _fail("OUT_INVALID", "--out must name a file, not a directory")
    if os.path.splitext(raw_name)[1].lower() != ".json" or os.path.splitext(name)[1].lower() != ".json":
        _fail("OUT_SUFFIX_NOT_JSON", "--out must end with .json (allow-list, nothing else is written)")
    if raw_name != name:
        _fail("OUT_INVALID", "--out is not a normalised file name (trailing dot or space, or . and ..)")
    if name.startswith(TMP_PREFIX):
        _fail("OUT_INVALID", f"--out must not start with {TMP_PREFIX}")
    if any(ord(ch) < 32 for ch in name):
        _fail("OUT_INVALID", "--out contains control characters")
    if os.name == "nt":
        if any(ch in _WIN_BAD_CHARS for ch in name) or os.path.splitext(name)[0].rstrip(" .").upper() in _WIN_RESERVED:
            _fail("OUT_INVALID", "--out is not a plain file name on Windows (stream, device name or reserved character)")

    # The report may never be one of the input files.
    for label, other in (("input", input_path), ("rules", rules_path)):
        other_abs = os.path.abspath(other)
        if _same_path(out_abs, other_abs) or _same_path(out_abs, os.path.realpath(other_abs)):
            _fail("OUT_IS_INPUT", f"--out is the {label} file")
        try:
            if os.path.samefile(out_abs, other_abs):
                _fail("OUT_IS_INPUT", f"--out is the same file as the {label} file")
        except OSError:
            pass  # out does not exist (the normal case) or the other file is unreadable here

    # The parent must be a real directory, reached without symlink, junction, reparse point or 8.3 short name.
    try:
        pst = os.lstat(parent)
    except OSError:
        _fail("OUT_PARENT_MISSING", "the parent directory of --out does not exist")
    if (stat.S_ISLNK(pst.st_mode) or not stat.S_ISDIR(pst.st_mode)
            or getattr(pst, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        _fail("OUT_PARENT_NOT_REAL_DIR", "the parent of --out is not a real directory (symlink, junction or reparse point)")
    real_parent = os.path.realpath(parent)
    if os.path.normcase(parent) != os.path.normcase(real_parent):
        _fail("OUT_PARENT_NOT_CANONICAL",
              f"the parent of --out resolves elsewhere ({real_parent}): a symlink, junction or 8.3 short name is on "
              "the path. Pass the full long path with no links in it.")
    for label, other in (("input", input_path), ("rules", rules_path)):
        folders = {os.path.dirname(os.path.abspath(other)), os.path.dirname(os.path.realpath(other))}
        if any(_inside(real_parent, f) or _inside(parent, f) for f in folders):
            _fail("OUT_IN_INPUT_DIR", f"the parent of --out is, or lies inside, the folder of the {label} file")

    # Nothing may exist under that name in any form (file, directory, symlink even if dangling, hard link, junction).
    try:
        os.lstat(out_abs)
    except FileNotFoundError:
        pass
    except OSError:
        _fail("OUT_EXISTS", "cannot rule out that --out exists")
    else:
        _fail("OUT_EXISTS", "--out already exists (no overwrite option)")
    return parent, name, (pst.st_dev, pst.st_ino)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    done = 0
    while done < len(data):
        n = os.write(fd, view[done:])
        if n <= 0:
            raise OSError("short write")
        done += n


def _remove_own_tmp(posix: bool, dfd, tmp_name: str, tmp_path) -> None:
    """Remove only the temporary file this run created. Errors are ignored: nothing else is touched."""
    try:
        if posix:
            os.unlink(tmp_name, dir_fd=dfd)
        else:
            os.unlink(tmp_path)
    except OSError:
        pass


def _verify(posix: bool, dfd, parent: str, name: str, digest: str, size: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    path = os.path.join(parent, name)
    st = os.lstat(name, dir_fd=dfd) if posix else os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size != size:
        _fail("OUT_VERIFY_FAILED", "the report exists under --out but is not a single regular file of the expected size; "
                                   "nothing was deleted")
    rfd = os.open(name, flags, dir_fd=dfd) if posix else os.open(path, flags)
    try:
        h = hashlib.sha256()
        while True:
            chunk = os.read(rfd, 1 << 20)
            if not chunk:
                break
            h.update(chunk)
    finally:
        os.close(rfd)
    if h.hexdigest() != digest:
        _fail("OUT_VERIFY_FAILED", "the report exists under --out but does not match what was built; nothing was deleted")


def _close_quietly(fd) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def write_report(out_path, data: bytes, input_path, rules_path) -> None:
    """Create out_path exclusively with `data`. Raises CadAuditError (exit code 3). Before the report is published a
    failure leaves no out file; after it is published nothing is deleted, and the message says so."""
    parent, name, parent_id = check_target(out_path, input_path, rules_path)
    digest = hashlib.sha256(data).hexdigest()
    tmp_name = TMP_PREFIX + secrets.token_hex(16) + ".json"
    posix = os.name != "nt"
    flags = (os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_CLOEXEC", 0))
    tmp_path = None if posix else os.path.join(parent, tmp_name)
    dfd = None
    fd = None
    tmp_made = False
    step = "START"      # START -> WRITE (temp exists) -> PUBLISH (link/rename running) -> LINKED (POSIX) -> PUBLISHED
    failure = None
    try:
        try:
            if posix:
                dfd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                              | getattr(os, "O_CLOEXEC", 0))
                opened = os.fstat(dfd)
                if parent_id != (opened.st_dev, opened.st_ino):     # identity seen by check_target, not a fresh lstat
                    _fail("OUT_PARENT_CHANGED", "the parent directory changed between the check and the write")
                fd = os.open(tmp_name, flags, 0o644, dir_fd=dfd)
            else:
                fd = os.open(tmp_path, flags, 0o644)
            tmp_made = True
            step = "WRITE"
            _write_all(fd, data)
            os.fsync(fd)
            done, fd = fd, None
            os.close(done)
            step = "PUBLISH"
            if posix:
                os.link(tmp_name, name, src_dir_fd=dfd, dst_dir_fd=dfd, follow_symlinks=False)  # fails if name exists
                step = "LINKED"          # the report name exists; the temporary name is still there
                os.unlink(tmp_name, dir_fd=dfd)
                tmp_made = False
            else:
                os.rename(tmp_path, os.path.join(parent, name))  # fails if name exists; never os.replace
                tmp_made = False
            step = "PUBLISHED"           # the report exists under its final name; only verification is left
            _verify(posix, dfd, parent, name, digest, len(data))
        except CadAuditError as e:
            failure = e
        except OSError as e:
            if isinstance(e, FileExistsError) and step == "PUBLISH":
                failure = CadAuditError("OUT_EXISTS", "--out appeared while writing; the existing file was not touched", exit_code=3)
            else:
                if step == "LINKED":
                    tail = ("the report exists under its final name; its temporary name could not be removed "
                            "(nothing else was deleted)")
                elif step == "PUBLISHED":
                    tail = "the report exists under its final name but could not be verified; nothing was deleted"
                else:
                    tail = "no report was written"
                failure = CadAuditError("OUT_WRITE_FAILED", f"{type(e).__name__} (errno {e.errno}); {tail}", exit_code=3)
    finally:
        # Order matters on Windows: the temporary file can only be removed after its handle is closed.
        if fd is not None:
            _close_quietly(fd)
        if tmp_made:
            _remove_own_tmp(posix, dfd, tmp_name, tmp_path)
        if dfd is not None:
            _close_quietly(dfd)
    if failure is not None:
        raise failure
