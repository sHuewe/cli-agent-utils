from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .cache_identity import project_cache_key
from .code_validator_types import CodeValidationError

_CACHE_SCHEMA = "cli-agent-gradle-cache-v5"

_GRADLE_REPOSITORY_URL_METADATA = "resource-at-url.bin"
_URL_SCHEME_MARKER = b"://"
_URL_AUTHORITY_TERMINATORS = b"/?#\x00\r\n\t "
_URL_TOKEN_TERMINATORS = b"\x00\r\n\t "


def _contains_url_userinfo(data: bytes) -> bool:
    """Return True when a byte buffer contains URL userinfo in an authority."""
    cursor = 0
    while True:
        marker = data.find(_URL_SCHEME_MARKER, cursor)
        if marker < 0:
            return False
        authority_start = marker + len(_URL_SCHEME_MARKER)
        authority_end = len(data)
        for delimiter in _URL_AUTHORITY_TERMINATORS:
            position = data.find(bytes((delimiter,)), authority_start)
            if position >= 0:
                authority_end = min(authority_end, position)
        at = data.find(b"@", authority_start, authority_end)
        if at >= 0:
            return True
        cursor = authority_start


def _contains_url_query(data: bytes) -> bool:
    """Return True when repository metadata contains a URL query component."""
    cursor = 0
    while True:
        marker = data.find(_URL_SCHEME_MARKER, cursor)
        if marker < 0:
            return False
        url_start = marker + len(_URL_SCHEME_MARKER)
        url_end = len(data)
        for delimiter in _URL_TOKEN_TERMINATORS:
            position = data.find(bytes((delimiter,)), url_start)
            if position >= 0:
                url_end = min(url_end, position)
        if data.find(b"?", url_start, url_end) >= 0:
            return True
        cursor = url_start


def _reject_credential_bearing_repository_metadata(modules: Path) -> None:
    """Reject Gradle repository metadata that embeds URL userinfo credentials."""
    for metadata_dir in modules.glob("metadata-*"):
        if metadata_dir.is_symlink():
            raise CodeValidationError(
                "Gradle-Metadatenverzeichnisse dürfen keine Symlinks sein."
            )
        if not metadata_dir.is_dir():
            continue
        for path in metadata_dir.rglob(_GRADLE_REPOSITORY_URL_METADATA):
            if path.is_symlink() or not path.is_file():
                raise CodeValidationError(
                    "Gradle-Repository-Metadaten müssen reguläre Dateien sein."
                )
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise CodeValidationError(
                    "Gradle-Repository-Metadaten konnten nicht geprüft werden."
                ) from exc
            if _contains_url_userinfo(payload) or _contains_url_query(payload):
                raise CodeValidationError(
                    "Der vorbereitete Gradle-Cache enthält Repository-URLs mit "
                    "eingebetteten Zugangsdaten oder Query-Parametern. Verwende "
                    "eine Gradle-Repository-Konfiguration ohne Credentials bzw. "
                    "sensitive Parameter in der URL."
                )


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


def gradle_dependency_key(
    project: Path,
    *,
    project_identity: str | None = None,
) -> str:
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise CodeValidationError(f"Gradle-Projekt existiert nicht: {root}")
    if not (
        (root / "build.gradle").is_file()
        or (root / "build.gradle.kts").is_file()
    ):
        raise CodeValidationError(
            "Gradle-Projekt benötigt build.gradle oder build.gradle.kts."
        )
    return project_cache_key(
        "gradle",
        root,
        project_identity=project_identity,
    )


def gradle_cache_entry(
    cache_root: Path,
    project: Path,
    *,
    project_identity: str | None = None,
) -> GradleCacheEntry:
    root = cache_root.expanduser().resolve()
    return GradleCacheEntry(
        root=root,
        key=gradle_dependency_key(project, project_identity=project_identity),
    )


def validate_gradle_cache_tree(directory: Path) -> int:
    root = directory.resolve()
    if directory.is_symlink() or not root.is_dir():
        raise CodeValidationError(
            "Der vorbereitete Gradle-Cache ist kein Verzeichnis."
        )
    total_bytes = 0

    def walk(current: Path) -> None:
        nonlocal total_bytes
        try:
            entries = os.scandir(current)
        except OSError as exc:
            raise CodeValidationError(
                "Der vorbereitete Gradle-Cache konnte nicht gelesen werden."
            ) from exc
        with entries:
            for entry in entries:
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise CodeValidationError(
                        "Ein Gradle-Cache-Eintrag konnte nicht geprüft werden."
                    ) from exc
                mode = info.st_mode
                if stat.S_ISLNK(mode):
                    raise CodeValidationError(
                        "Symlinks sind im vorbereiteten Gradle-Cache nicht erlaubt."
                    )
                if stat.S_ISDIR(mode):
                    walk(path)
                elif stat.S_ISREG(mode):
                    total_bytes += info.st_size
                else:
                    raise CodeValidationError(
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
            raise CodeValidationError(
                f"Gradle-User-Konfiguration darf kein Symlink sein: {src}"
            )
        if src.is_file():
            dst = target_home / name
            shutil.copy2(src, dst)
            copied.append(dst)

    init_source = source / "init.d"
    if init_source.is_symlink():
        raise CodeValidationError(
            f"Gradle-User-Konfiguration darf kein Symlink sein: {init_source}"
        )
    if init_source.is_dir():
        init_target = target_home / "init.d"
        init_target.mkdir(parents=True, exist_ok=True)
        for child in sorted(init_source.iterdir()):
            if child.is_symlink() or not child.is_file():
                raise CodeValidationError(
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
            raise CodeValidationError(
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
        raise CodeValidationError(
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
            _reject_credential_bearing_repository_metadata(modules)
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
