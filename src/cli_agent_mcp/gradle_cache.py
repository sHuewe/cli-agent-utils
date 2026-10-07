from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .test_validator_types import TestValidationError

_CACHE_SCHEMA = "cli-agent-gradle-cache-v2"
_IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "out",
    "target",
    "venv",
}
_RELEVANT_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
    "gradle-wrapper.properties",
    "gradle-wrapper.jar",
    "libs.versions.toml",
    "verification-metadata.xml",
}


@dataclass(frozen=True)
class GradleCacheEntry:
    root: Path
    key: str

    @property
    def directory(self) -> Path:
        return self.root / self.key

    @property
    def gradle_home(self) -> Path:
        return self.directory / "gradle-home"

    @property
    def metadata_file(self) -> Path:
        return self.directory / "cache.json"

    def is_ready(self) -> bool:
        if (
            self.directory.is_symlink()
            or self.gradle_home.is_symlink()
            or self.metadata_file.is_symlink()
            or not self.gradle_home.is_dir()
            or not self.metadata_file.is_file()
        ):
            return False
        try:
            metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            isinstance(metadata, dict)
            and metadata.get("schema") == _CACHE_SCHEMA
            and metadata.get("key") == self.key
            and metadata.get("ready") is True
        )


def default_gradle_cache_root() -> Path:
    return Path.home() / ".cli-agent" / "dependency-cache" / "gradle"


def default_source_gradle_user_home() -> Path:
    configured = os.environ.get("GRADLE_USER_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".gradle").resolve()


def _iter_relevant_files(project: Path) -> tuple[Path, ...]:
    result: list[Path] = []

    def walk(directory: Path, *, include_all_regular_files: bool = False) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise TestValidationError(
                f"Gradle-Projekt konnte nicht gelesen werden: {directory}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise TestValidationError(
                    f"Gradle-Projektpfad konnte nicht geprüft werden: {path}"
                ) from exc
            if stat.S_ISLNK(mode):
                raise TestValidationError(
                    f"Symlink in Gradle-Konfiguration ist nicht erlaubt: "
                    f"{path.relative_to(project)}"
                )
            if stat.S_ISDIR(mode):
                if entry.name in _IGNORED_DIRECTORIES:
                    continue
                walk(
                    path,
                    include_all_regular_files=(
                        include_all_regular_files or path == project / "buildSrc"
                    ),
                )
            elif stat.S_ISREG(mode):
                if (
                    include_all_regular_files
                    or entry.name in _RELEVANT_NAMES
                    or entry.name.endswith(".gradle")
                    or entry.name.endswith(".gradle.kts")
                    or entry.name.endswith(".versions.toml")
                ):
                    result.append(path)

    walk(project)
    return tuple(result)


def gradle_dependency_key(project: Path) -> str:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise TestValidationError(f"Gradle-Projekt existiert nicht: {root}")
    if not (
        (root / "build.gradle").is_file()
        or (root / "build.gradle.kts").is_file()
    ):
        raise TestValidationError(
            "Gradle-Projekt benötigt build.gradle oder build.gradle.kts."
        )

    files = sorted(
        _iter_relevant_files(root),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    digest.update((_CACHE_SCHEMA + "\0").encode("utf-8"))
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise TestValidationError(
                f"Gradle-Konfigurationsdatei konnte nicht gelesen werden: {relative}"
            ) from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        digest.update(b"\0")
    return "gradle-" + digest.hexdigest()


def gradle_cache_entry(cache_root: Path, project: Path) -> GradleCacheEntry:
    root = cache_root.expanduser().resolve()
    return GradleCacheEntry(root=root, key=gradle_dependency_key(project))


def validate_gradle_cache_tree(directory: Path) -> int:
    root = directory.resolve()
    if directory.is_symlink() or not root.is_dir():
        raise TestValidationError(
            "Der vorbereitete Gradle-Cache ist kein Verzeichnis."
        )
    total_bytes = 0

    def walk(current: Path) -> None:
        nonlocal total_bytes
        try:
            entries = os.scandir(current)
        except OSError as exc:
            raise TestValidationError(
                "Der vorbereitete Gradle-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise TestValidationError(
                        "Ein Gradle-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                mode = info.st_mode
                if stat.S_ISLNK(mode):
                    raise TestValidationError(
                        "Symlinks sind im vorbereiteten Gradle-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    total_bytes += info.st_size
                else:
                    raise TestValidationError(
                        "Der Gradle-Cache darf nur reguläre Dateien und "
                        "Verzeichnisse enthalten."
                    )

    walk(root)
    return total_bytes


def seed_gradle_user_configuration(
    source_home: Path,
    target_home: Path,
) -> tuple[Path, ...]:
    """Copy only user configuration needed for preparation, never caches."""
    copied: list[Path] = []
    source = source_home.expanduser().resolve()
    if not source.is_dir():
        return ()

    for name in ("gradle.properties", "init.gradle", "init.gradle.kts"):
        src = source / name
        if src.is_symlink():
            raise TestValidationError(
                f"Gradle-User-Konfiguration darf kein Symlink sein: {src}"
            )
        if src.is_file():
            dst = target_home / name
            shutil.copy2(src, dst)
            copied.append(dst)

    init_source = source / "init.d"
    if init_source.is_symlink():
        raise TestValidationError(
            f"Gradle-User-Konfiguration darf kein Symlink sein: {init_source}"
        )
    if init_source.is_dir():
        init_target = target_home / "init.d"
        init_target.mkdir(parents=True, exist_ok=True)
        for child in sorted(init_source.iterdir()):
            if child.is_symlink() or not child.is_file():
                raise TestValidationError(
                    "Gradle init.d darf für die Cache-Vorbereitung nur "
                    "reguläre Dateien enthalten."
                )
            destination = init_target / child.name
            shutil.copy2(child, destination)
            copied.append(destination)
    return tuple(copied)


def remove_seeded_gradle_user_configuration(
    target_home: Path,
    copied: tuple[Path, ...],
) -> None:
    for path in copied:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise TestValidationError(
                "Temporär kopierte Gradle-User-Konfiguration konnte nicht "
                "entfernt werden."
            ) from exc
    init_dir = target_home / "init.d"
    if init_dir.is_dir():
        try:
            init_dir.rmdir()
        except OSError:
            pass


def sanitize_gradle_home_for_promotion(target_home: Path) -> None:
    """Keep only downloaded module-cache content needed for offline resolution.

    Preparation may evaluate user Gradle init scripts or properties containing
    credentials. Gradle can compile those scripts into caches below the Gradle
    user home, so deleting only the source files is not a sufficient secret
    boundary. Promote only the dependency module cache and discard all script,
    DSL, daemon, wrapper, native and other generated state.
    """
    home = target_home.resolve()
    if target_home.is_symlink() or not home.is_dir():
        raise TestValidationError(
            "Der temporäre Gradle-User-Home ist kein sicheres Verzeichnis."
        )

    modules = home / "caches" / "modules-2"
    sanitized = home.parent / "gradle-home-sanitized"
    if sanitized.exists():
        shutil.rmtree(sanitized)
    sanitized.mkdir(parents=True)
    try:
        if modules.exists():
            validate_gradle_cache_tree(modules)
            destination = sanitized / "caches" / "modules-2"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(modules, destination)
        shutil.rmtree(home)
        sanitized.replace(home)
    except BaseException:
        shutil.rmtree(sanitized, ignore_errors=True)
        raise


def write_gradle_ready_metadata(directory: Path, key: str) -> None:
    (directory / "cache.json").write_text(
        json.dumps(
            {
                "schema": _CACHE_SCHEMA,
                "key": key,
                "ready": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
