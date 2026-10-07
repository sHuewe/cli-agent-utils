from __future__ import annotations

import io
import os
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path

from .test_validator_types import TestValidationError

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


def _is_windows_reparse_point(file_stat: object) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_flag)


def _is_same_file(
    expected: os.stat_result,
    actual: os.stat_result,
) -> bool:
    return (
        expected.st_dev == actual.st_dev
        and expected.st_ino == actual.st_ino
        and stat.S_IFMT(expected.st_mode) == stat.S_IFMT(actual.st_mode)
    )


def _open_verified_regular_file(
    path: Path,
    expected: os.stat_result,
):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise TestValidationError(
            f"Projektdatei konnte nicht erneut geprüft werden: {path}"
        ) from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or _is_windows_reparse_point(before)
        or not stat.S_ISREG(before.st_mode)
        or not _is_same_file(expected, before)
    ):
        raise TestValidationError(
            f"Projektdatei wurde während der Snapshot-Erstellung verändert: {path}"
        )

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TestValidationError(
            f"Projektdatei konnte nicht sicher geöffnet werden: {path}"
        ) from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_windows_reparse_point(opened)
            or not _is_same_file(expected, opened)
            or opened.st_size != expected.st_size
        ):
            raise TestValidationError(
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


def _safe_tree_files(
    root: Path,
    *,
    max_file_bytes: int,
    max_project_bytes: int,
) -> tuple[tuple[tuple[Path, os.stat_result], ...], int]:
    files: list[tuple[Path, os.stat_result]] = []
    total_bytes = 0

    def walk(directory: Path) -> None:
        nonlocal total_bytes
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise TestValidationError(
                f"Projektverzeichnis konnte nicht gelesen werden: {directory}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                entry_stat = entry.stat(follow_symlinks=False)
                mode = entry_stat.st_mode
            except OSError as exc:
                raise TestValidationError(
                    f"Projektpfad konnte nicht geprüft werden: {path}"
                ) from exc
            if _is_windows_reparse_point(entry_stat):
                raise TestValidationError(
                    "Windows-Reparse-Points/Junctions sind im Test-Snapshot "
                    f"nicht erlaubt: {path.relative_to(root)}"
                )
            if stat.S_ISLNK(mode):
                raise TestValidationError(
                    f"Symlinks sind im Test-Snapshot nicht erlaubt: "
                    f"{path.relative_to(root)}"
                )
            if stat.S_ISDIR(mode):
                relative = path.relative_to(root)
                if entry.name in _IGNORED_DIRECTORY_NAMES:
                    continue
                if _is_build_output_directory(root, path):
                    continue
                walk(path)
                continue
            if not stat.S_ISREG(mode):
                raise TestValidationError(
                    f"Nur reguläre Dateien und Verzeichnisse sind erlaubt: "
                    f"{path.relative_to(root)}"
                )
            size = entry_stat.st_size
            if size > max_file_bytes:
                raise TestValidationError(
                    f"Datei überschreitet das Größenlimit: {path.relative_to(root)}"
                )
            total_bytes += size
            if total_bytes > max_project_bytes:
                raise TestValidationError("Projekt überschreitet das Größenlimit.")
            files.append((path, entry_stat))

    walk(root)
    return tuple(files), total_bytes


def create_project_snapshot(
    project: Path,
    *,
    max_file_bytes: int,
    max_project_bytes: int,
) -> ProjectSnapshot:
    root = project.resolve()
    if not root.is_dir():
        raise TestValidationError(f"Projekt existiert nicht: {root}")
    entries, total_bytes = _safe_tree_files(
        root,
        max_file_bytes=max_file_bytes,
        max_project_bytes=max_project_bytes,
    )
    files = tuple(path for path, _ in entries)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path, expected in entries:
            relative = path.relative_to(root)
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
