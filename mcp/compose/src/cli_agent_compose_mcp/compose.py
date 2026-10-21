from __future__ import annotations

import logging
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

COMPOSE_FILENAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


class ComposeError(RuntimeError):
    """A Docker Compose command could not be executed."""


def find_compose_file(project_directory: Path) -> Path:
    project_directory = project_directory.resolve()
    if not project_directory.is_dir():
        raise ComposeError(f"Projektverzeichnis existiert nicht: {project_directory}")
    existing = [project_directory / name for name in COMPOSE_FILENAMES if (project_directory / name).is_file()]
    if not existing:
        raise ComposeError(
            f"Keine Compose-Datei in {project_directory} gefunden "
            f"(erwartet: {', '.join(COMPOSE_FILENAMES)})."
        )
    try:
        resolved = existing[0].resolve(strict=True)
        resolved.relative_to(project_directory)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ComposeError(
            "Die Compose-Datei muss innerhalb des festgelegten Projektverzeichnisses liegen."
        ) from exc
    return resolved


@dataclass(frozen=True)
class ComposeProject:
    directory: Path
    compose_file: Path
    wsl: bool = False

    @classmethod
    def from_directory(cls, directory: Path, *, wsl: bool = False) -> "ComposeProject":
        resolved = directory.resolve()
        return cls(resolved, find_compose_file(resolved), wsl)

    def command(self, *arguments: str) -> list[str]:
        docker_cmd = ["wsl", "docker", "compose"] if self.wsl else ["docker", "compose"]
        return [*docker_cmd, "-f", str(self.compose_file), *arguments]

    def run(self, *arguments: str, timeout: int = 60) -> str:
        command = self.command(*arguments)
        logger.info("Running compose command executable=%r cwd=%r", shutil.which(command[0]), str(self.directory))
        try:
            completed = subprocess.run(  # nosec B603
                command,
                cwd=self.directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ComposeError("Die Docker-CLI wurde nicht gefunden.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ComposeError(f"Zeitüberschreitung bei Docker Compose nach {timeout} Sekunden.") from exc
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise ComposeError(f"Docker Compose endete mit Code {completed.returncode}: {details}")
        return "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip()).strip()

    def services(self) -> list[str]:
        return [line.strip() for line in self.run("config", "--services").splitlines() if line.strip()]

    def validate_service(self, service_name: str) -> str:
        if not service_name or service_name != service_name.strip():
            raise ComposeError("Der Servicename darf nicht leer sein.")
        services = self.services()
        if service_name not in services:
            raise ComposeError(f"Unbekannter Service {service_name!r}. Verfügbar: {', '.join(services) if services else '(keine)'}")
        return service_name

    def read_compose_file(self) -> str:
        return self.compose_file.read_text(encoding="utf-8")

    def ps(self) -> str:
        return self.run("ps")

    def up_all(self) -> str:
        return self.run("up", "-d", timeout=120)

    def start(self, service_name: str) -> str:
        return self.run("up", "-d", self.validate_service(service_name), timeout=120)

    def stop(self, service_name: str) -> str:
        return self.run("stop", self.validate_service(service_name), timeout=120)

    def restart(self, service_name: str) -> str:
        return self.run("restart", self.validate_service(service_name), timeout=120)

    def logs(self, service_name: str) -> str:
        return self.run("logs", "--tail", "200", "--no-color", self.validate_service(service_name))
