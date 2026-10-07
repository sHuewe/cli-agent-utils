from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import subprocess  # nosec B404
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .test_validator_types import TestValidationError

_CACHE_SCHEMA = "cli-agent-python-cache-v2"
_STANDARD_REQUIREMENTS = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "requirements-tests.txt",
)
_OPTIONAL_DEPENDENCY_GROUPS = {"dev", "development", "test", "tests"}
_INCLUDE_RE = re.compile(
    r"^\s*(?:-r|--requirement|-c|--constraint)(?:\s+|=)([^#\s]+)"
)


@dataclass(frozen=True)
class PythonDependencyPlan:
    requirement_files: tuple[str, ...]
    dependency_specs: tuple[str, ...]

    @property
    def has_dependencies(self) -> bool:
        return bool(self.requirement_files or self.dependency_specs)


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
        if self.install_manifest_file.is_symlink() or not self.install_manifest_file.is_file():
            raise TestValidationError(
                "Der Python-Cache enthält kein gültiges Offline-Installationsmanifest."
            )
        try:
            value = json.loads(self.install_manifest_file.read_text(encoding="utf-8"))
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
    relative_to: Path | None = None,
) -> Path:
    raw = value.replace("\\", "/")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts:
        raise TestValidationError(
            f"Requirements-Include muss innerhalb des Projekts liegen: {value!r}"
        )
    base = relative_to if relative_to is not None else project
    candidate = (base / Path(*pure.parts)).resolve()
    try:
        candidate.relative_to(project)
    except ValueError as exc:
        raise TestValidationError(
            f"Requirements-Include verweist außerhalb des Projekts: {value!r}"
        ) from exc
    if candidate.is_symlink():
        raise TestValidationError(
            f"Requirements-Datei darf kein Symlink sein: {value!r}"
        )
    if not candidate.is_file():
        raise TestValidationError(
            f"Requirements-Datei existiert nicht: {value!r}"
        )
    return candidate


def _requirement_files(project: Path) -> tuple[Path, ...]:
    roots = [
        project / name
        for name in _STANDARD_REQUIREMENTS
        if (project / name).is_file()
    ]
    result: dict[str, Path] = {}

    def add(path: Path) -> None:
        if path.is_symlink():
            raise TestValidationError(
                f"Requirements-Datei darf kein Symlink sein: "
                f"{path.relative_to(project)}"
            )
        relative = path.relative_to(project).as_posix()
        if relative in result:
            return
        result[relative] = path
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise TestValidationError(
                f"Requirements-Datei konnte nicht gelesen werden: {relative}"
            ) from exc
        for line in text.splitlines():
            match = _INCLUDE_RE.match(line)
            if match:
                included = _safe_relative_project_file(
                    project,
                    match.group(1),
                    relative_to=path.parent,
                )
                add(included)

    for path in roots:
        add(path)
    return tuple(result[name] for name in sorted(result))


def python_dependency_plan(project: Path) -> PythonDependencyPlan:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise TestValidationError(f"Python-Projekt existiert nicht: {root}")

    unsupported_lockfiles = [
        name
        for name in ("uv.lock", "poetry.lock", "Pipfile.lock")
        if (root / name).is_file()
    ]
    if unsupported_lockfiles:
        joined = ", ".join(unsupported_lockfiles)
        raise TestValidationError(
            "Lockfile-basierte Python-Dependency-Auflösung wird vom "
            f"Test-Validator nicht unterstützt ({joined}). Exportiere die "
            "gewünschten, gepinnten Test-Dependencies in eine unterstützte "
            "requirements*.txt-Datei und entferne das Lockfile für diesen "
            "Validator-Lauf."
        )

    requirement_files = _requirement_files(root)
    top_level_requirements = tuple(
        name
        for name in _STANDARD_REQUIREMENTS
        if (root / name).is_file()
    )

    dependency_specs: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_symlink():
        raise TestValidationError("pyproject.toml darf kein Symlink sein.")
    if pyproject.is_file():
        try:
            config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise TestValidationError(
                "pyproject.toml konnte nicht gelesen werden."
            ) from exc
        project_config = config.get("project")
        if isinstance(project_config, dict):
            dependencies = project_config.get("dependencies", [])
            if isinstance(dependencies, list):
                dependency_specs.extend(
                    str(value)
                    for value in dependencies
                    if isinstance(value, str) and value.strip()
                )
            optional = project_config.get("optional-dependencies", {})
            if isinstance(optional, dict):
                for group in sorted(_OPTIONAL_DEPENDENCY_GROUPS):
                    values = optional.get(group, [])
                    if isinstance(values, list):
                        dependency_specs.extend(
                            str(value)
                            for value in values
                            if isinstance(value, str) and value.strip()
                        )
        groups = config.get("dependency-groups")
        if isinstance(groups, dict):
            def expand_group(name: str, stack: tuple[str, ...] = ()) -> list[str]:
                if name in stack:
                    chain = " -> ".join((*stack, name))
                    raise TestValidationError(
                        f"Zyklischer dependency-group Include: {chain}"
                    )
                values = groups.get(name)
                if values is None:
                    raise TestValidationError(
                        f"Unbekannte dependency-group: {name}"
                    )
                if not isinstance(values, list):
                    raise TestValidationError(
                        f"dependency-group {name!r} muss eine Liste sein."
                    )

                expanded: list[str] = []
                for value in values:
                    if isinstance(value, str):
                        if value.strip():
                            expanded.append(value)
                        continue
                    if isinstance(value, dict) and set(value) == {"include-group"}:
                        included = value.get("include-group")
                        if not isinstance(included, str) or not included.strip():
                            raise TestValidationError(
                                f"Ungültiger include-group Eintrag in {name!r}."
                            )
                        expanded.extend(
                            expand_group(included, (*stack, name))
                        )
                        continue
                    raise TestValidationError(
                        f"Nicht unterstützter dependency-group Eintrag in {name!r}."
                    )
                return expanded

            for group in sorted(_OPTIONAL_DEPENDENCY_GROUPS):
                if group in groups:
                    dependency_specs.extend(expand_group(group))

    # Included requirement files affect the key even though pip receives only
    # the top-level files and resolves nested -r/-c entries itself.
    _ = requirement_files
    return PythonDependencyPlan(
        requirement_files=top_level_requirements,
        dependency_specs=tuple(dict.fromkeys(dependency_specs)),
    )


def python_dependency_key(project: Path) -> str:
    root = project.expanduser().resolve()
    plan = python_dependency_plan(root)
    files = list(_requirement_files(root))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        files.append(pyproject)
    files = sorted(
        set(files),
        key=lambda path: path.relative_to(root).as_posix(),
    )

    digest = hashlib.sha256()
    digest.update((_CACHE_SCHEMA + "\0").encode("utf-8"))
    for path in files:
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        digest.update(b"\0")
    for spec in plan.dependency_specs:
        digest.update(b"spec\0")
        digest.update(spec.encode("utf-8"))
        digest.update(b"\0")
    return "python-" + digest.hexdigest()


def python_cache_entry(cache_root: Path, project: Path) -> PythonCacheEntry:
    root = cache_root.expanduser().resolve()
    return PythonCacheEntry(root=root, key=python_dependency_key(project))


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
) -> None:
    wheels = directory / "wheels"
    wheel_names = sorted(
        path.name
        for path in wheels.iterdir()
        if path.is_file() and not path.is_symlink() and path.name.endswith(".whl")
    )
    if plan.has_dependencies and not wheel_names:
        raise TestValidationError(
            "Python-Cache enthält trotz deklarierter Dependencies keine Wheels."
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
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "machine": platform.machine(),
                "requirement_files": list(plan.requirement_files),
                "dependency_specs": list(plan.dependency_specs),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
