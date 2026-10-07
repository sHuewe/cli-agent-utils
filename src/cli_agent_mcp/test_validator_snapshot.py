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
) -> tuple[tuple[Path, ...], int]:
    files: list[Path] = []
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
            size = entry.stat(follow_symlinks=False).st_size
            if size > max_file_bytes:
                raise TestValidationError(
                    f"Datei überschreitet das Größenlimit: {path.relative_to(root)}"
                )
            total_bytes += size
            if total_bytes > max_project_bytes:
                raise TestValidationError("Projekt überschreitet das Größenlimit.")
            files.append(path)

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
    files, total_bytes = _safe_tree_files(
        root,
        max_file_bytes=max_file_bytes,
        max_project_bytes=max_project_bytes,
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in files:
            relative = path.relative_to(root)
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = 65532
            info.gid = 65532
            info.uname = ""
            info.gname = ""
            info.mode = info.mode & 0o777
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return ProjectSnapshot(
        archive=buffer.getvalue(),
        files=files,
        total_bytes=total_bytes,
    )
