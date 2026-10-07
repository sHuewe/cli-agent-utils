from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _is_windows_reparse_point(file_stat: object) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_flag)


def _same_file(expected: os.stat_result, actual: os.stat_result) -> bool:
    return (
        expected.st_dev == actual.st_dev
        and expected.st_ino == actual.st_ino
        and stat.S_IFMT(expected.st_mode) == stat.S_IFMT(actual.st_mode)
    )


def _validate_directory_stat(
    path: Path,
    expected: os.stat_result,
    actual: os.stat_result,
    error_type: type[Exception],
    message: str,
) -> None:
    if (
        stat.S_ISLNK(actual.st_mode)
        or _is_windows_reparse_point(actual)
        or not stat.S_ISDIR(actual.st_mode)
        or not _same_file(expected, actual)
    ):
        raise error_type(f"{message}: {path}")


@contextmanager
def verified_directory_scandir(
    path: Path,
    expected: os.stat_result,
    *,
    error_type: type[Exception],
    changed_message: str,
) -> Iterator[os.ScandirIterator[str]]:
    """Open and verify a directory before enumerating it.

    On POSIX, enumeration is bound to an O_NOFOLLOW directory descriptor.
    On Windows, a reparse-point-safe directory handle is kept open without
    FILE_SHARE_DELETE for the full enumeration. This prevents the directory
    itself from being replaced while scandir uses its pathname.
    """
    if os.name != "nt":
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
        if not directory_flag or not nofollow_flag:
            raise error_type(
                "Sichere Directory-Descriptor-Traversierung wird auf dieser "
                f"Plattform nicht unterstützt: {path}"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd: int | None = None
        try:
            fd = os.open(path, flags | directory_flag | nofollow_flag)
            opened = os.fstat(fd)
            _validate_directory_stat(
                path,
                expected,
                opened,
                error_type,
                changed_message,
            )
            with os.scandir(fd) as scanner:
                yield scanner
        except error_type:
            raise
        except OSError as exc:
            raise error_type(f"{changed_message}: {path}") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        return

    import ctypes
    from ctypes import wintypes

    FILE_READ_ATTRIBUTES = 0x0080
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        FILE_READ_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise error_type(f"{changed_message}: {path}")

    try:
        # The handle was opened without FILE_SHARE_DELETE and with
        # OPEN_REPARSE_POINT. While it is held, the directory itself cannot be
        # replaced by a junction/symlink. Revalidate the path only after that
        # lock is in place, then keep the handle alive for the whole scan.
        try:
            opened = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise error_type(f"{changed_message}: {path}") from exc
        _validate_directory_stat(
            path,
            expected,
            opened,
            error_type,
            changed_message,
        )
        with os.scandir(path) as scanner:
            yield scanner
    finally:
        close_handle(handle)
