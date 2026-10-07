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
                yield path
                yield from walk(path)
            elif stat.S_ISREG(entry_stat.st_mode):
                yield path
            else:
                raise ValueError(
                    f"Unsupported filesystem entry in streamed directory: {path}"
                )

    yield from walk(source)


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
                    for path in _iter_safe_stream_paths(source):
                        relative = path.relative_to(source).as_posix()
                        if path.is_dir():
                            info = archive.gettarinfo(str(path), arcname=relative)
                            info.uid = 65532
                            info.gid = 65532
                            info.uname = ""
                            info.gname = ""
                            archive.addfile(info)
                        elif path.is_file():
                            info = archive.gettarinfo(str(path), arcname=relative)
                            info.uid = 65532
                            info.gid = 65532
                            info.uname = ""
                            info.gname = ""
                            with path.open("rb") as handle:
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
