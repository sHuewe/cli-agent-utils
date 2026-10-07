from __future__ import annotations

import hashlib
import json
import os
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .test_validator_types import TestValidationError

_CACHE_SCHEMA = "cli-agent-maven-cache-v3"
_IGNORED_DIRECTORIES = {
    ".git",
    ".gradle",
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
    "target",
    "venv",
}
def default_maven_cache_root() -> Path:
    return Path.home() / ".cli-agent" / "dependency-cache" / "maven"


_ROOT_MAVEN_FILES = (
    ".mvn/maven.config",
    ".mvn/extensions.xml",
    ".mvn/jvm.config",
)


@dataclass(frozen=True)
class MavenCacheEntry:
    root: Path
    key: str

    @property
    def directory(self) -> Path:
        return self.root / self.key

    @property
    def repository(self) -> Path:
        return self.directory / "repository"

    @property
    def metadata_file(self) -> Path:
        return self.directory / "cache.json"

    def is_ready(self) -> bool:
        if (
            self.directory.is_symlink()
            or self.repository.is_symlink()
            or self.metadata_file.is_symlink()
            or not self.repository.is_dir()
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


def _reject_reactor_modules(root_pom: Path) -> None:
    try:
        root = ET.parse(root_pom).getroot()
    except (OSError, ET.ParseError) as exc:
        raise TestValidationError(
            "Die Root-pom.xml konnte nicht sicher ausgewertet werden."
        ) from exc

    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "modules":
            continue
        if any(
            child.tag.rsplit("}", 1)[-1] == "module"
            and (child.text or "").strip()
            for child in element
        ):
            raise TestValidationError(
                "Maven-Multi-Module-/Reaktor-Projekte werden vom v1-"
                "Offline-Validator noch nicht unterstützt. Verwende vorerst "
                "ein Single-Module-Projekt ohne <modules>."
            )


def maven_dependency_key(project: Path) -> str:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise TestValidationError(f"Maven-Projekt existiert nicht: {root}")
    root_pom = root / "pom.xml"
    if root_pom.is_symlink():
        raise TestValidationError("Die Root-pom.xml darf kein Symlink sein.")
    if not root_pom.is_file():
        raise TestValidationError("Maven-Projekt benötigt eine pom.xml.")

    _reject_reactor_modules(root_pom)
    files = [root_pom]
    for relative_name in _ROOT_MAVEN_FILES:
        candidate = root / relative_name
        if candidate.is_symlink():
            raise TestValidationError(
                f"Maven-Konfigurationsdatei darf kein Symlink sein: {relative_name}"
            )
        if candidate.is_file():
            files.append(candidate)
    files = sorted(set(files), key=lambda path: path.relative_to(root).as_posix())

    digest = hashlib.sha256()
    digest.update((_CACHE_SCHEMA + "\0").encode("utf-8"))
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise TestValidationError(
                f"Maven-Konfigurationsdatei konnte nicht gelesen werden: {relative}"
            ) from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        digest.update(b"\0")
    return "maven-" + digest.hexdigest()


def cache_entry(cache_root: Path, project: Path) -> MavenCacheEntry:
    root = cache_root.expanduser().resolve()
    return MavenCacheEntry(root=root, key=maven_dependency_key(project))


def validate_repository_tree(repository: Path) -> int:
    root = repository.resolve()
    if repository.is_symlink() or not root.is_dir():
        raise TestValidationError("Der vorbereitete Maven-Cache ist kein Verzeichnis.")
    total_bytes = 0

    def walk(directory: Path) -> None:
        nonlocal total_bytes
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            raise TestValidationError(
                "Der vorbereitete Maven-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except OSError as exc:
                    raise TestValidationError(
                        "Ein Maven-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                if stat.S_ISLNK(mode):
                    raise TestValidationError(
                        "Symlinks sind im vorbereiteten Maven-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    total_bytes += entry.stat(follow_symlinks=False).st_size
                else:
                    raise TestValidationError(
                        "Der Maven-Cache darf nur reguläre Dateien und "
                        "Verzeichnisse enthalten."
                    )

    walk(root)
    return total_bytes


def sanitize_repository_for_offline_use(repository: Path) -> None:
    """Remove remote-origin tracking that is not reproducible in the sandbox."""
    root = repository.resolve()
    if repository.is_symlink() or not root.is_dir():
        raise TestValidationError(
            "Der vorbereitete Maven-Cache ist kein Verzeichnis."
        )

    def walk(directory: Path) -> None:
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            raise TestValidationError(
                "Der vorbereitete Maven-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except OSError as exc:
                    raise TestValidationError(
                        "Ein Maven-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                if stat.S_ISLNK(mode):
                    raise TestValidationError(
                        "Symlinks sind im vorbereiteten Maven-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    if entry.name == "_remote.repositories":
                        try:
                            path.unlink()
                        except OSError as exc:
                            raise TestValidationError(
                                "Maven-Repository-Provenienz konnte nicht "
                                "bereinigt werden."
                            ) from exc
                else:
                    raise TestValidationError(
                        "Der Maven-Cache darf nur reguläre Dateien und "
                        "Verzeichnisse enthalten."
                    )

    walk(root)


def write_ready_metadata(directory: Path, key: str) -> None:
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

