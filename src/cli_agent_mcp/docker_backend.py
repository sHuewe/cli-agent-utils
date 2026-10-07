from __future__ import annotations

import os
import subprocess  # nosec B404
import stat
import tarfile
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from dataclasses import dataclass


def _is_windows_reparse_point(file_stat: object) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_flag)


def _iter_safe_stream_paths(source: Path):
    try:
        source_stat = os.stat(source, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"Streamed directory could not be inspected: {source}") from exc
    if stat.S_ISLNK(source_stat.st_mode) or _is_windows_reparse_point(source_stat):
        raise ValueError(
            f"Symlink/reparse point streamed directory is not allowed: {source}"
        )
    if not stat.S_ISDIR(source_stat.st_mode):
        raise ValueError(f"Streamed path is not a directory: {source}")

    def walk(directory: Path):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ValueError(
                f"Streamed directory could not be read: {directory}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(
                    f"Streamed path could not be inspected: {path}"
                ) from exc
            if (
                stat.S_ISLNK(entry_stat.st_mode)
                or _is_windows_reparse_point(entry_stat)
            ):
                raise ValueError(
                    "Symlink/reparse point in streamed directory is not allowed: "
                    f"{path}"
                )
            if stat.S_ISDIR(entry_stat.st_mode):
                yield path, entry_stat
                yield from walk(path)
            elif stat.S_ISREG(entry_stat.st_mode):
                yield path, entry_stat
            else:
                raise ValueError(
                    f"Unsupported filesystem entry in streamed directory: {path}"
                )

    yield from walk(source)


def _same_file(expected: os.stat_result, actual: os.stat_result) -> bool:
    return (
        expected.st_dev == actual.st_dev
        and expected.st_ino == actual.st_ino
        and stat.S_IFMT(expected.st_mode) == stat.S_IFMT(actual.st_mode)
    )


def _open_verified_stream_file(path: Path, expected: os.stat_result):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"Streamed file could not be re-inspected: {path}") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or _is_windows_reparse_point(before)
        or not stat.S_ISREG(before.st_mode)
        or not _same_file(expected, before)
    ):
        raise ValueError(f"Streamed file changed during transfer: {path}")

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"Streamed file could not be safely opened: {path}") from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_windows_reparse_point(opened)
            or not _same_file(expected, opened)
            or opened.st_size != expected.st_size
        ):
            raise ValueError(f"Streamed file changed during transfer: {path}")
        return os.fdopen(fd, "rb", closefd=True), opened
    except BaseException:
        os.close(fd)
        raise


@dataclass(frozen=True)
class DockerCommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[..., subprocess.CompletedProcess[object]]


class DockerBackend:
    """Small Docker CLI adapter supporting native Docker and Docker through WSL."""

    def __init__(
        self,
        *,
        wsl: bool = False,
        wsl_distribution: str | None = None,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        self.wsl = wsl
        self.wsl_distribution = (
            wsl_distribution.strip() if wsl_distribution else None
        )
        self._run_command = command_runner

    def command(self, *arguments: str) -> list[str]:
        if not self.wsl:
            return ["docker", *arguments]
        prefix = ["wsl"]
        if self.wsl_distribution:
            prefix.extend(["-d", self.wsl_distribution])
        return [*prefix, "--", "docker", *arguments]

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout: float,
        input_bytes: bytes | None = None,
    ) -> DockerCommandResult:
        command = self.command(*arguments)
        if input_bytes is None:
            completed = self._run_command(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout = str(completed.stdout or "")
            stderr = str(completed.stderr or "")
        else:
            completed = self._run_command(
                command,
                input=input_bytes,
                capture_output=True,
                text=False,
                timeout=timeout,
                check=False,
            )
            stdout_value = completed.stdout or b""
            stderr_value = completed.stderr or b""
            if isinstance(stdout_value, bytes):
                stdout = stdout_value.decode("utf-8", errors="replace")
            else:
                stdout = str(stdout_value)
            if isinstance(stderr_value, bytes):
                stderr = stderr_value.decode("utf-8", errors="replace")
            else:
                stderr = str(stderr_value)
        return DockerCommandResult(
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )


    def stream_tar_directory(
        self,
        source: Path,
        arguments: Sequence[str],
        *,
        timeout: float,
    ) -> DockerCommandResult:
        """Stream a host directory as TAR to a Docker command without a temp archive."""
        command = self.command(*arguments)
        process = subprocess.Popen(  # nosec B603
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        stdin = process.stdin
        process.stdin = None
        writer_error: list[BaseException] = []

        def write_archive() -> None:
            try:
                with tarfile.open(fileobj=stdin, mode="w|") as archive:
                    for path, expected in _iter_safe_stream_paths(source):
                        relative = path.relative_to(source).as_posix()
                        if stat.S_ISDIR(expected.st_mode):
                            info = tarfile.TarInfo(relative)
                            info.type = tarfile.DIRTYPE
                            info.mode = stat.S_IMODE(expected.st_mode)
                            info.mtime = int(expected.st_mtime)
                            info.uid = 65532
                            info.gid = 65532
                            info.uname = ""
                            info.gname = ""
                            archive.addfile(info)
                        elif stat.S_ISREG(expected.st_mode):
                            handle, opened = _open_verified_stream_file(path, expected)
                            with handle:
                                info = tarfile.TarInfo(relative)
                                info.size = opened.st_size
                                info.mode = stat.S_IMODE(opened.st_mode)
                                info.mtime = int(opened.st_mtime)
                                info.uid = 65532
                                info.gid = 65532
                                info.uname = ""
                                info.gname = ""
                                archive.addfile(info, handle)
                        else:
                            raise ValueError(
                                "Unsupported filesystem entry in streamed "
                                f"directory: {path}"
                            )
            except BaseException as exc:
                writer_error.append(exc)
            finally:
                try:
                    stdin.close()
                except OSError:
                    pass

        writer = threading.Thread(target=write_archive, daemon=True)
        writer.start()
        try:
            # communicate() drains stdout/stderr while the writer streams stdin.
            # The timeout therefore covers the transfer as well as extraction.
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            writer.join(timeout=1)
            raise
        writer.join(timeout=1)
        if writer.is_alive():
            process.kill()
            process.communicate()
            raise subprocess.TimeoutExpired(command, timeout)
        if writer_error:
            raise writer_error[0]
        return DockerCommandResult(
            returncode=process.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
