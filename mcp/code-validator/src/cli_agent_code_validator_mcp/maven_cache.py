from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .cache_identity import project_cache_key
from .code_validator_types import CodeValidationError

_CACHE_SCHEMA = "cli-agent-maven-cache-v5"
_MAVEN_TRANSIENT_FILES = {"_remote.repositories", "resolver-status.properties"}

# Test execution resolves providers loaded dynamically by Maven Surefire that
# dependency:go-offline and package -DskipTests may leave unprepared.
# Explicitly override ambient Maven skip properties for the warm-up only.
MAVEN_TEST_WARMUP_ARGS = (
    "-DskipTests=false",
    "-Dmaven.test.skip=false",
    "-Dmaven.test.skip.exec=false",
    "-Dmaven.test.failure.ignore=true",
    "test",
)
_WINDOWS = os.name == "nt"


def _is_maven_transient_name(name: str) -> bool:
    return name in _MAVEN_TRANSIENT_FILES or name.endswith(".lastUpdated")


def _unlink_maven_metadata(path: Path) -> None:
    """Remove transient metadata; tolerate disappearance at any cleanup stage."""
    try:
        try:
            path.unlink()
        except PermissionError:
            if not _WINDOWS or path.is_symlink():
                raise
            mode = path.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode) or mode & stat.S_IWRITE:
                raise
            # Windows cannot unlink files with the read-only attribute. Only
            # change the selected metadata file, never other cache artifacts.
            path.chmod(mode | stat.S_IWRITE)
            path.unlink()
    except FileNotFoundError:
        # A concurrent process may remove resolver metadata at any step:
        # initial unlink, stat, chmod or the retrying unlink.
        return


def remove_maven_temporary_cache(directory: Path) -> None:
    """Remove a temporary repository even if Maven made files read-only on Windows."""
    def onerror(function, name: str, exc_info) -> None:
        original = exc_info[1]
        path = Path(name)
        if not _WINDOWS or not isinstance(original, PermissionError) or path.is_symlink():
            raise original
        mode = path.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode) or mode & stat.S_IWRITE:
            raise original
        path.chmod(mode | stat.S_IWRITE)
        function(name)

    shutil.rmtree(directory, onerror=onerror)


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


def maven_dependency_key(
    project: Path,
    *,
    project_identity: str | None = None,
) -> str:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise CodeValidationError(f"Maven-Projekt existiert nicht: {root}")
    root_pom = root / "pom.xml"
    if root_pom.is_symlink():
        raise CodeValidationError("Die Root-pom.xml darf kein Symlink sein.")
    if not root_pom.is_file():
        raise CodeValidationError("Maven-Projekt benötigt eine pom.xml.")
    return project_cache_key(
        "maven",
        root,
        project_identity=project_identity,
    )


def cache_entry(
    cache_root: Path,
    project: Path,
    *,
    project_identity: str | None = None,
) -> MavenCacheEntry:
    root = cache_root.expanduser().resolve()
    return MavenCacheEntry(
        root=root,
        key=maven_dependency_key(project, project_identity=project_identity),
    )


def validate_repository_tree(repository: Path) -> int:
    root = repository.resolve()
    if repository.is_symlink() or not root.is_dir():
        raise CodeValidationError("Der vorbereitete Maven-Cache ist kein Verzeichnis.")
    total_bytes = 0

    def walk(directory: Path) -> None:
        nonlocal total_bytes
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            raise CodeValidationError(
                "Der vorbereitete Maven-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except OSError as exc:
                    raise CodeValidationError(
                        "Ein Maven-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                if stat.S_ISLNK(mode):
                    raise CodeValidationError(
                        "Symlinks sind im vorbereiteten Maven-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    total_bytes += entry.stat(follow_symlinks=False).st_size
                else:
                    raise CodeValidationError(
                        "Der Maven-Cache darf nur reguläre Dateien und "
                        "Verzeichnisse enthalten."
                    )

    walk(root)
    return total_bytes


def sanitize_repository_for_offline_use(repository: Path) -> None:
    """Keep the offline artifact repository, but drop resolver-only provenance/state."""
    root = repository.resolve()
    if repository.is_symlink() or not root.is_dir():
        raise CodeValidationError(
            "Der vorbereitete Maven-Cache ist kein Verzeichnis."
        )

    def walk(directory: Path) -> None:
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            raise CodeValidationError(
                "Der vorbereitete Maven-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except FileNotFoundError as exc:
                    if _is_maven_transient_name(entry.name):
                        # Metadata was removed between scandir and stat.
                        continue
                    raise CodeValidationError(
                        "Ein Maven-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                except OSError as exc:
                    raise CodeValidationError(
                        "Ein Maven-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                if stat.S_ISLNK(mode):
                    raise CodeValidationError(
                        "Symlinks sind im vorbereiteten Maven-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    if _is_maven_transient_name(entry.name):
                        try:
                            _unlink_maven_metadata(path)
                        except OSError as exc:
                            # Local, operator-invoked CLI only: include the
                            # failing file and OS reason for actionable diagnosis.
                            raise CodeValidationError(
                                "Maven-Repository-Metadaten konnten nicht "
                                f"bereinigt werden: {path} ({exc})."
                            ) from exc
                else:
                    raise CodeValidationError(
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

