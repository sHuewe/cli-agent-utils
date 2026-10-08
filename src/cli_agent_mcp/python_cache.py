from __future__ import annotations

import json
import os
import platform
import re
import stat
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .cache_identity import project_cache_key
from .test_validator_types import TestValidationError

_CACHE_SCHEMA = "cli-agent-python-cache-v5"
_REQUIREMENTS_FILE = "requirements.txt"
_DEFAULT_MAX_REQUIREMENT_FILE_BYTES = 16 * 1024 * 1024
_INCLUDE_RE = re.compile(
    r"^\s*(?:(?:-r|-c)\s*=?\s*([^\s]+)|"
    r"(?:--requirement|--constraint)(?:\s+|=)\s*([^\s]+))\s*$"
)
_FROZEN_REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9.!+_-]*$"
)


@dataclass(frozen=True)
class PythonDependencyPlan:
    requirement_files: tuple[str, ...] = (_REQUIREMENTS_FILE,)

    @property
    def has_dependencies(self) -> bool:
        # requirements.txt is the explicit dependency contract for the validator.
        # Even an empty file is prepared once so environment markers and future
        # edits are handled consistently through the cache key.
        return True


@dataclass(frozen=True)
class PythonCacheEntry:
    root: Path
    key: str

    @property
    def directory(self) -> Path:
        return self.root / self.key

    @property
    def wheels(self) -> Path:
        return self.directory / "wheels"

    @property
    def metadata_file(self) -> Path:
        return self.directory / "cache.json"

    @property
    def install_manifest_file(self) -> Path:
        return self.wheels / "install-manifest.json"

    def install_wheel_names(self) -> tuple[str, ...]:
        if (
            self.install_manifest_file.is_symlink()
            or not self.install_manifest_file.is_file()
        ):
            raise TestValidationError(
                "Der Python-Cache enthält kein gültiges Offline-Installationsmanifest."
            )
        try:
            value = json.loads(
                self.install_manifest_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise TestValidationError(
                "Das Python-Offline-Installationsmanifest konnte nicht gelesen werden."
            ) from exc
        if not isinstance(value, list):
            raise TestValidationError(
                "Das Python-Offline-Installationsmanifest ist ungültig."
            )
        names: list[str] = []
        for item in value:
            if (
                not isinstance(item, str)
                or not item
                or Path(item).name != item
                or not item.endswith(".whl")
            ):
                raise TestValidationError(
                    "Das Python-Offline-Installationsmanifest enthält einen "
                    "ungültigen Wheel-Namen."
                )
            wheel = self.wheels / item
            if wheel.is_symlink() or not wheel.is_file():
                raise TestValidationError(
                    f"Vorbereitetes Wheel fehlt oder ist unsicher: {item}"
                )
            names.append(item)
        return tuple(names)

    def metadata(self) -> dict[str, object] | None:
        if (
            self.directory.is_symlink()
            or self.wheels.is_symlink()
            or self.metadata_file.is_symlink()
            or self.install_manifest_file.is_symlink()
            or not self.wheels.is_dir()
            or not self.metadata_file.is_file()
            or not self.install_manifest_file.is_file()
        ):
            return None
        try:
            value = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        if (
            value.get("schema") != _CACHE_SCHEMA
            or value.get("key") != self.key
            or value.get("ready") is not True
            or value.get("prepared_under_wsl") is not True
        ):
            return None
        return value

    def is_ready(self) -> bool:
        return self.metadata() is not None


def default_python_cache_root() -> Path:
    return Path.home() / ".cli-agent" / "dependency-cache" / "python"


def is_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        version = Path("/proc/version").read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return False
    return "microsoft" in version.casefold()


def require_wsl() -> None:
    if not is_wsl():
        raise RuntimeError(
            "Python-Dependencies müssen unter WSL vorbereitet werden, damit "
            "Linux-kompatible Wheels für den Docker-Testcontainer entstehen. "
            "Starte cli-agent-test-cache prepare-python innerhalb von WSL."
        )


def default_wsl_windows_cache_root(cache_name: str) -> Path:
    """Resolve a Windows user's cli-agent cache root as a WSL path."""
    require_wsl()
    if not cache_name or "/" in cache_name or "\\" in cache_name:
        raise ValueError("Ungültiger Cache-Name.")
    try:
        profile = subprocess.run(  # nosec B603
            ["cmd.exe", "/d", "/c", "echo %USERPROFILE%"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Windows-Benutzerprofil konnte aus WSL nicht ermittelt werden. "
            "Verwende --cache-root mit einem Verzeichnis auf einem Windows-"
            "Mount, das der Windows-Validator ebenfalls lesen kann."
        ) from exc
    windows_home = profile.stdout.strip()
    if profile.returncode != 0 or not windows_home or "%" in windows_home:
        raise RuntimeError(
            "Windows-Benutzerprofil konnte aus WSL nicht ermittelt werden. "
            "Verwende --cache-root explizit."
        )
    try:
        converted = subprocess.run(  # nosec B603
            ["wslpath", "-u", windows_home],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "wslpath ist nicht verfügbar. Verwende --cache-root explizit."
        ) from exc
    linux_home = converted.stdout.strip()
    if converted.returncode != 0 or not linux_home:
        raise RuntimeError(
            "Windows-Benutzerprofil konnte nicht in einen WSL-Pfad "
            "umgewandelt werden. Verwende --cache-root explizit."
        )
    return Path(linux_home) / ".cli-agent" / "dependency-cache" / cache_name


def default_wsl_python_cache_root() -> Path:
    """Backward-compatible helper for the Windows Python cache from WSL."""
    return default_wsl_windows_cache_root("python")


def _safe_relative_project_file(
    project: Path,
    value: str,
    *,
    relative_to: Path,
) -> Path:
    raw = value.replace("\\", "/")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts:
        raise TestValidationError(
            "Requirements-Include muss innerhalb des Projekts liegen."
        )
    candidate = (relative_to / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(project)
    except ValueError as exc:
        raise TestValidationError(
            "Requirements-Include verweist außerhalb des Projekts."
        ) from exc
    if candidate.is_symlink():
        raise TestValidationError(
            "Requirements-Include darf kein Symlink sein."
        )
    if not candidate.is_file():
        raise TestValidationError(
            "Requirements-Include verweist auf keine vorhandene Datei."
        )
    return candidate


def _strip_requirement_comment(line: str) -> str:
    """Strip pip-style comments without treating URL/path fragments as comments."""
    left = line.lstrip()
    if left.startswith("#"):
        return ""
    for index, char in enumerate(line):
        if char == "#" and index > 0 and line[index - 1].isspace():
            return line[:index].rstrip()
    return line.strip()


def _validate_frozen_requirement_line(relative: str, line: str) -> None:
    """Validate the deliberately small requirements.txt subset supported in v1."""
    candidate = _strip_requirement_comment(line)
    if not candidate:
        return
    if _INCLUDE_RE.match(candidate):
        return
    if candidate.startswith("-"):
        option_name = candidate
        if candidate.startswith("--"):
            option_name = candidate.split(None, 1)[0].split("=", 1)[0]
        elif len(candidate) >= 2:
            option_name = candidate[:2]
        raise TestValidationError(
            "requirements.txt unterstützt im Test-Validator nur gepinnte "
            "Pakete sowie -r/--requirement und -c/--constraint. "
            f"Nicht unterstützte Option in {relative}: {option_name!r}"
        )
    if _FROZEN_REQUIREMENT_RE.fullmatch(candidate) is None:
        raise TestValidationError(
            "requirements.txt muss für den Test-Validator ausschließlich "
            "eingefrorene Index-Abhängigkeiten im Format package==version "
            "enthalten. Pfade, URLs, VCS-Referenzen und Marker werden nicht "
            f"unterstützt ({relative})."
        )


def _requirement_files(
    project: Path,
    *,
    max_file_bytes: int = _DEFAULT_MAX_REQUIREMENT_FILE_BYTES,
) -> tuple[Path, ...]:
    root = project / _REQUIREMENTS_FILE
    if root.is_symlink():
        raise TestValidationError("requirements.txt darf kein Symlink sein.")
    if not root.is_file():
        raise TestValidationError(
            "Python-Test-Validierung benötigt eine requirements.txt im "
            "Projektroot. Erzeuge sie in der aktivierten Projektumgebung z. B. "
            "mit 'python -m pip freeze --exclude-editable > requirements.txt'."
        )

    result: dict[str, Path] = {}

    def add(path: Path) -> None:
        if path.is_symlink():
            raise TestValidationError(
                "Requirements-Datei darf kein Symlink sein: "
                f"{path.relative_to(project)}"
            )
        relative = path.relative_to(project).as_posix()
        if relative in result:
            return
        result[relative] = path
        try:
            size = path.stat(follow_symlinks=False).st_size
            if size > max_file_bytes:
                raise TestValidationError(
                    f"Requirements-Datei überschreitet das Größenlimit: {relative}"
                )
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(max_file_bytes + 1)
            if len(text.encode("utf-8", errors="replace")) > max_file_bytes:
                raise TestValidationError(
                    f"Requirements-Datei überschreitet das Größenlimit: {relative}"
                )
        except OSError as exc:
            raise TestValidationError(
                f"Requirements-Datei konnte nicht gelesen werden: {relative}"
            ) from exc
        for raw_line in text.splitlines():
            line = _strip_requirement_comment(raw_line)
            if not line:
                continue
            match = _INCLUDE_RE.match(line)
            if match:
                include_value = match.group(1) or match.group(2)
                included = _safe_relative_project_file(
                    project,
                    include_value,
                    relative_to=path.parent,
                )
                add(included)
                continue
            _validate_frozen_requirement_line(relative, line)

    add(root)
    return tuple(result[name] for name in sorted(result))


def python_dependency_plan(
    project: Path,
    *,
    max_file_bytes: int = _DEFAULT_MAX_REQUIREMENT_FILE_BYTES,
) -> PythonDependencyPlan:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise TestValidationError(f"Python-Projekt existiert nicht: {root}")
    if max_file_bytes <= 0:
        raise ValueError("max_file_bytes muss positiv sein.")
    _requirement_files(root, max_file_bytes=max_file_bytes)
    return PythonDependencyPlan()


def python_dependency_key(
    project: Path,
    *,
    project_identity: str | None = None,
    max_file_bytes: int = _DEFAULT_MAX_REQUIREMENT_FILE_BYTES,
) -> str:
    root = project.expanduser().resolve()
    python_dependency_plan(root, max_file_bytes=max_file_bytes)
    return project_cache_key(
        "python",
        root,
        project_identity=project_identity,
    )


def python_cache_entry(
    cache_root: Path,
    project: Path,
    *,
    project_identity: str | None = None,
    max_file_bytes: int = _DEFAULT_MAX_REQUIREMENT_FILE_BYTES,
) -> PythonCacheEntry:
    root = cache_root.expanduser().resolve()
    return PythonCacheEntry(
        root=root,
        key=python_dependency_key(
            project,
            project_identity=project_identity,
            max_file_bytes=max_file_bytes,
        ),
    )


def validate_python_cache_tree(directory: Path) -> int:
    root = directory.resolve()
    if directory.is_symlink() or not root.is_dir():
        raise TestValidationError(
            "Der vorbereitete Python-Cache ist kein Verzeichnis."
        )
    total_bytes = 0

    def walk(current: Path) -> None:
        nonlocal total_bytes
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise TestValidationError(
                        "Symlinks sind im vorbereiteten Python-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    total_bytes += entry.stat(follow_symlinks=False).st_size
                else:
                    raise TestValidationError(
                        "Der Python-Cache darf nur reguläre Dateien und "
                        "Verzeichnisse enthalten."
                    )

    walk(root)
    return total_bytes


def write_python_ready_metadata(
    directory: Path,
    key: str,
    plan: PythonDependencyPlan,
    *,
    interpreter_metadata: dict[str, str] | None = None,
) -> None:
    wheels = directory / "wheels"
    wheel_names = sorted(
        path.name
        for path in wheels.iterdir()
        if path.is_file() and not path.is_symlink() and path.name.endswith(".whl")
    )
    (wheels / "install-manifest.json").write_text(
        json.dumps(wheel_names, indent=2) + "\n",
        encoding="utf-8",
    )
    (directory / "cache.json").write_text(
        json.dumps(
            {
                "schema": _CACHE_SCHEMA,
                "key": key,
                "ready": True,
                "prepared_under_wsl": True,
                "python_version": (
                    interpreter_metadata["python_version"]
                    if interpreter_metadata is not None
                    else platform.python_version()
                ),
                "python_implementation": (
                    interpreter_metadata["python_implementation"]
                    if interpreter_metadata is not None
                    else platform.python_implementation()
                ),
                "machine": (
                    interpreter_metadata["machine"]
                    if interpreter_metadata is not None
                    else platform.machine()
                ),
                "requirement_files": list(plan.requirement_files),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
