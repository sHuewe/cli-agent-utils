from __future__ import annotations

import io
import os
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path

from .filesystem_safety import (
    _same_file,
    _is_windows_reparse_point,
    verified_directory_scandir,
)
from .code_validator_types import CodeValidationError

_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    ".cli-agent",
    "node_modules",
    "venv",
}
_ROOT_BUILD_OUTPUT_DIRECTORIES = {
    ".gradle",
    "build",
    "dist",
    "target",
}

def _is_build_output_directory(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if len(relative.parts) == 1 and path.name in _ROOT_BUILD_OUTPUT_DIRECTORIES:
        return True

    parent = path.parent
    if path.name == "target" and (parent / "pom.xml").is_file():
        return True
    if path.name in {"build", ".gradle"} and (
        (parent / "build.gradle").is_file()
        or (parent / "build.gradle.kts").is_file()
    ):
        return True
    if path.name == "dist" and (
        (parent / "pyproject.toml").is_file()
        or (parent / "setup.py").is_file()
        or (parent / "setup.cfg").is_file()
    ):
        return True
    return False


def _open_verified_regular_file(
    path: Path,
    expected: os.stat_result,
):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise CodeValidationError(
            f"Projektdatei konnte nicht erneut geprüft werden: {path}"
        ) from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or _is_windows_reparse_point(before)
        or not stat.S_ISREG(before.st_mode)
        or not _same_file(expected, before)
    ):
        raise CodeValidationError(
            f"Projektdatei wurde während der Snapshot-Erstellung verändert: {path}"
        )

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CodeValidationError(
            f"Projektdatei konnte nicht sicher geöffnet werden: {path}"
        ) from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_windows_reparse_point(opened)
            or not _same_file(expected, opened)
            or opened.st_size != expected.st_size
        ):
            raise CodeValidationError(
                f"Projektdatei wurde während der Snapshot-Erstellung verändert: {path}"
            )
        return os.fdopen(fd, "rb", closefd=True), opened
    except BaseException:
        os.close(fd)
        raise


@dataclass(frozen=True)
class ProjectSnapshot:
    archive: bytes
    files: tuple[Path, ...]
    total_bytes: int


def _safe_tree_entries(
    root: Path,
    *,
    max_file_bytes: int,
    max_project_bytes: int,
    max_snapshot_entries: int,
) -> tuple[tuple[tuple[Path, os.stat_result], ...], int]:
    entries_for_archive: list[tuple[Path, os.stat_result]] = []
    total_bytes = 0
    entry_count = 0

    try:
        root_stat = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise CodeValidationError(
            f"Projektverzeichnis konnte nicht geprüft werden: {root}"
        ) from exc
    if (
        stat.S_ISLNK(root_stat.st_mode)
        or _is_windows_reparse_point(root_stat)
        or not stat.S_ISDIR(root_stat.st_mode)
    ):
        raise CodeValidationError(
            f"Projektroot ist kein sicheres Verzeichnis: {root}"
        )

    def walk(directory: Path, expected: os.stat_result) -> None:
        nonlocal total_bytes, entry_count
        try:
            with verified_directory_scandir(
                directory,
                expected,
                error_type=CodeValidationError,
                changed_message=(
                    "Projektverzeichnis wurde während der "
                    "Snapshot-Erstellung verändert"
                ),
            ) as scanned:
                for entry in scanned:
                    entry_count += 1
                    if entry_count > max_snapshot_entries:
                        raise CodeValidationError(
                            "Projekt überschreitet das Snapshot-Eintragslimit."
                        )
                    path = directory / entry.name
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                        mode = entry_stat.st_mode
                    except OSError as exc:
                        raise CodeValidationError(
                            f"Projektpfad konnte nicht geprüft werden: {path}"
                        ) from exc
                    if _is_windows_reparse_point(entry_stat):
                        raise CodeValidationError(
                            "Windows-Reparse-Points/Junctions sind im "
                            "Test-Snapshot nicht erlaubt: "
                            f"{path.relative_to(root)}"
                        )
                    if stat.S_ISLNK(mode):
                        raise CodeValidationError(
                            "Symlinks sind im Test-Snapshot nicht erlaubt: "
                            f"{path.relative_to(root)}"
                        )
                    if stat.S_ISDIR(mode):
                        if entry.name in _IGNORED_DIRECTORY_NAMES:
                            continue
                        if _is_build_output_directory(root, path):
                            continue
                        entries_for_archive.append((path, entry_stat))
                        walk(path, entry_stat)
                        continue
                    if not stat.S_ISREG(mode):
                        raise CodeValidationError(
                            "Nur reguläre Dateien und Verzeichnisse sind erlaubt: "
                            f"{path.relative_to(root)}"
                        )
                    size = entry_stat.st_size
                    if size > max_file_bytes:
                        raise CodeValidationError(
                            "Datei überschreitet das Größenlimit: "
                            f"{path.relative_to(root)}"
                        )
                    total_bytes += size
                    if total_bytes > max_project_bytes:
                        raise CodeValidationError(
                            "Projekt überschreitet das Größenlimit."
                        )
                    entries_for_archive.append((path, entry_stat))
        except CodeValidationError:
            raise
        except OSError as exc:
            raise CodeValidationError(
                f"Projektverzeichnis konnte nicht sicher gelesen werden: {directory}"
            ) from exc

    walk(root, root_stat)
    return tuple(entries_for_archive), total_bytes


def create_project_snapshot(
    project: Path,
    *,
    max_file_bytes: int,
    max_project_bytes: int,
    max_snapshot_entries: int = 20_000,
) -> ProjectSnapshot:
    root = Path(os.path.abspath(project.expanduser()))
    entries, total_bytes = _safe_tree_entries(
        root,
        max_file_bytes=max_file_bytes,
        max_project_bytes=max_project_bytes,
        max_snapshot_entries=max_snapshot_entries,
    )
    files = tuple(
        path
        for path, entry_stat in entries
        if stat.S_ISREG(entry_stat.st_mode)
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path, expected in entries:
            relative = path.relative_to(root)
            if stat.S_ISDIR(expected.st_mode):
                info = tarfile.TarInfo(relative.as_posix())
                info.type = tarfile.DIRTYPE
                info.mtime = int(expected.st_mtime)
                info.mode = stat.S_IMODE(expected.st_mode)
                info.uid = 65532
                info.gid = 65532
                info.uname = ""
                info.gname = ""
                archive.addfile(info)
                continue

            handle, opened = _open_verified_regular_file(path, expected)
            with handle:
                info = tarfile.TarInfo(relative.as_posix())
                info.size = opened.st_size
                info.mtime = int(opened.st_mtime)
                info.mode = stat.S_IMODE(opened.st_mode)
                info.uid = 65532
                info.gid = 65532
                info.uname = ""
                info.gname = ""
                archive.addfile(info, handle)
    return ProjectSnapshot(
        archive=buffer.getvalue(),
        files=files,
        total_bytes=total_bytes,
    )
