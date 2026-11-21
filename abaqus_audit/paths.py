"""Restrict the CLI to explicit local paths and fresh output directories."""
import os
import stat
from pathlib import Path, PureWindowsPath


def _check_local(path):
    if os.name == "nt":
        from ctypes import windll

        # Reject device/UNC paths and mapped network drives before using them.
        if not path.drive or path.drive.startswith("\\\\") or windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise ValueError("Windows network and device paths are unsupported")
    elif str(path).startswith("//"):
        raise ValueError("Network paths are unsupported")


def _reserved_windows_component(name):
    if hasattr(os.path, "isreserved"):
        return os.path.isreserved(name)
    return (PureWindowsPath(name).is_reserved() or name.endswith((" ", "."))
            or any(char in name for char in ':*?"<>|') or any(ord(char) < 32 for char in name))


def local_path(value):
    path = Path(os.path.abspath(value))
    _check_local(path)
    # Inspect each existing component before resolving it so that a junction or
    # symlink to a UNC share cannot be followed while resolving a child.
    resolved = Path(path.anchor)
    for part in path.parts[1:]:
        candidate = resolved / part
        if os.name == "nt" and _reserved_windows_component(part):
            raise ValueError("Reserved Windows filename components are unsupported")
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            resolved = candidate
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Symbolic links and Windows reparse points are unsupported")
        resolved = candidate
    return resolved


def require_regular(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular file")


def prepare_directories(output, local):
    if local is not None and (output == local or output in local.parents or local in output.parents):
        raise ValueError("Aggregate and local evidence directories must be separate")
    for path in (output, local):
        if path is not None:
            if path.exists():
                raise FileExistsError("Choose a new output directory")
            if not path.parent.is_dir():
                raise ValueError("The output directory's parent must exist")
    output.mkdir(mode=0o700)
    if local is not None:
        local.mkdir(mode=0o700)
