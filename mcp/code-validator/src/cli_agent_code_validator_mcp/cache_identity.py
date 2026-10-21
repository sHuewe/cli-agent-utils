from __future__ import annotations

import hashlib
import sys
from pathlib import Path, PureWindowsPath

_CACHE_KEY_SCHEMA = "cli-agent-project-cache-v1"
_CACHE_KINDS = {"maven", "gradle", "python"}


def windows_project_identity(path: str) -> str:
    value = PureWindowsPath(path)
    if not value.is_absolute():
        raise ValueError("Windows-Projektpfad muss absolut sein.")
    normalized = value.as_posix().rstrip("/").casefold()
    return f"windows:{normalized}"


def native_project_identity(project: Path) -> str:
    root = project.expanduser().resolve()
    if sys.platform == "win32":
        return windows_project_identity(str(root))
    return f"posix:{root.as_posix().rstrip('/')}"


def project_cache_key(
    kind: str,
    project: Path,
    *,
    project_identity: str | None = None,
) -> str:
    if kind not in _CACHE_KINDS:
        raise ValueError(f"Unbekannter Cache-Typ: {kind!r}")
    identity = project_identity or native_project_identity(project)
    digest = hashlib.sha256()
    digest.update(_CACHE_KEY_SCHEMA.encode("utf-8"))
    digest.update(b"\0")
    digest.update(kind.encode("ascii"))
    digest.update(b"\0")
    digest.update(identity.encode("utf-8"))
    return f"{kind}-{digest.hexdigest()}"
