from __future__ import annotations

import subprocess  # nosec B404
from collections.abc import Callable, Sequence
from dataclasses import dataclass


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
