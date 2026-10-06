from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import uuid
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Literal

from .docker_backend import DockerBackend, DockerCommandResult
from .test_validator_redaction import OutputRedactor, discover_secret_values
from .test_validator_snapshot import create_project_snapshot
from .test_validator_types import TestValidationError, TestValidatorSettings

_JAVA_SELECTOR = re.compile(r"^[A-Za-z0-9_.$*#\[\],-]+$")
_MAX_SELECTOR_CHARS = 512


class DockerTestValidator:
    """Run fixed Python or Java test commands in a hardened short-lived container."""

    def __init__(
        self,
        workspace: Path,
        settings: TestValidatorSettings,
        *,
        backend: DockerBackend | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise TestValidationError(
                f"Projekt-Workspace existiert nicht: {self.workspace}"
            )
        self.settings = settings
        self.backend = backend or DockerBackend()

    def _resolve_project(self, project_path: str) -> Path:
        if not isinstance(project_path, str) or not project_path.strip():
            raise TestValidationError("Der Projektpfad darf nicht leer sein.")
        candidate = Path(project_path)
        windows = PureWindowsPath(project_path)
        if candidate.is_absolute() or windows.is_absolute() or windows.drive:
            raise TestValidationError(
                "Der Projektpfad muss relativ zum Workspace sein."
            )
        if ".." in PurePath(project_path).parts or ".." in windows.parts:
            raise TestValidationError(
                "Der Projektpfad darf '..' nicht enthalten."
            )
        resolved = (self.workspace / candidate).resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise TestValidationError(
                "Der Projektpfad verweist außerhalb des Workspaces."
            ) from exc
        if not resolved.is_dir():
            raise TestValidationError(
                f"Projekt existiert nicht: {project_path!r}"
            )
        return resolved

    @staticmethod
    def _validate_selector(selector: str | None, *, java: bool) -> str | None:
        if selector is None:
            return None
        if not isinstance(selector, str):
            raise TestValidationError("Der Test-Selector muss ein String sein.")
        value = selector.strip()
        if not value:
            raise TestValidationError("Der Test-Selector darf nicht leer sein.")
        if len(value) > _MAX_SELECTOR_CHARS:
            raise TestValidationError("Der Test-Selector ist zu lang.")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise TestValidationError(
                "Der Test-Selector darf keine Steuerzeichen enthalten."
            )
        if java and not _JAVA_SELECTOR.fullmatch(value):
            raise TestValidationError("Ungültiger Java-Test-Selector.")
        return value

    @staticmethod
    def _detect_java_build_system(
        project: Path,
        requested: Literal["auto", "maven", "gradle"],
    ) -> Literal["maven", "gradle"]:
        has_maven = (project / "pom.xml").is_file()
        has_gradle = (
            (project / "build.gradle").is_file()
            or (project / "build.gradle.kts").is_file()
        )
        if requested == "maven":
            if not has_maven:
                raise TestValidationError(
                    "build_system='maven' benötigt eine pom.xml."
                )
            return "maven"
        if requested == "gradle":
            if not has_gradle:
                raise TestValidationError(
                    "build_system='gradle' benötigt build.gradle oder build.gradle.kts."
                )
            return "gradle"
        if has_maven and has_gradle:
            raise TestValidationError(
                "Java-Buildsystem ist mehrdeutig; setze build_system auf "
                "'maven' oder 'gradle'."
            )
        if has_maven:
            return "maven"
        if has_gradle:
            return "gradle"
        raise TestValidationError(
            "Kein unterstütztes Java-Buildsystem gefunden "
            "(pom.xml/build.gradle/build.gradle.kts)."
        )

    def _docker(
        self,
        arguments: list[str],
        *,
        timeout: float,
        input_bytes: bytes | None = None,
    ) -> DockerCommandResult:
        return self.backend.run(
            arguments,
            timeout=timeout,
            input_bytes=input_bytes,
        )

    def _create_container(self, name: str, image: str) -> DockerCommandResult:
        return self._docker(
            [
                "create",
                "--name",
                name,
                "--init",
                "--pull",
                "never",
                "--user",
                "65532:65532",
                "--read-only",
                "--tmpfs",
                (
                    "/tmp:rw,nosuid,nodev,"
                    f"size={self.settings.tmp_tmpfs_size},"
                    "uid=65532,gid=65532,mode=0700"
                ),
                "--tmpfs",
                (
                    "/work:rw,nosuid,nodev,"
                    f"size={self.settings.work_tmpfs_size},"
                    "uid=65532,gid=65532,mode=0700"
                ),
                "--network",
                "none",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                str(self.settings.pids_limit),
                "--memory",
                self.settings.memory_limit,
                "--cpus",
                self.settings.cpu_limit,
                "--env",
                "HOME=/tmp/home",
                "--entrypoint",
                "sh",
                image,
                "-c",
                "while :; do sleep 3600; done",
            ],
            timeout=self.settings.setup_timeout_seconds,
        )

    def _verify_container_policy(self, name: str) -> dict[str, Any]:
        result = self._docker(
            ["inspect", name],
            timeout=self.settings.setup_timeout_seconds,
        )
        if result.returncode != 0:
            raise TestValidationError("Docker-Sandbox konnte nicht geprüft werden.")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise TestValidationError(
                "Docker-Sandbox lieferte ungültige Inspect-Daten."
            ) from exc
        if not isinstance(payload, list) or len(payload) != 1:
            raise TestValidationError(
                "Docker-Sandbox lieferte unerwartete Inspect-Daten."
            )
        config = payload[0].get("Config") or {}
        host = payload[0].get("HostConfig") or {}
        mounts = payload[0].get("Mounts") or []
        tmpfs = host.get("Tmpfs") or {}
        security_opt = host.get("SecurityOpt") or []
        cap_drop = host.get("CapDrop") or []
        checks = {
            "network_none": host.get("NetworkMode") == "none",
            "read_only_root": host.get("ReadonlyRootfs") is True,
            "non_root_user": config.get("User") == "65532:65532",
            "capabilities_dropped": "ALL" in cap_drop,
            "no_new_privileges": any(
                str(value).startswith("no-new-privileges")
                for value in security_opt
            ),
            "not_privileged": host.get("Privileged") is False,
            "no_host_binds": not bool(host.get("Binds")),
            "only_expected_mounts": all(
                isinstance(mount, dict)
                and mount.get("Type") == "tmpfs"
                and mount.get("Destination") in {"/tmp", "/work"}
                for mount in mounts
            ),
            "tmpfs_work": "/work" in tmpfs,
            "tmpfs_tmp": "/tmp" in tmpfs,
        }
        if not all(checks.values()):
            failed = ", ".join(
                name for name, success in checks.items() if not success
            )
            raise TestValidationError(
                f"Docker-Sandbox entspricht nicht der erwarteten Policy: {failed}"
            )
        return checks

    def _bounded(self, value: str) -> str:
        if len(value) <= self.settings.max_output_chars:
            return value
        return (
            value[: self.settings.max_output_chars]
            + "\n[Testausgabe wegen Größenlimit abgeschnitten]"
        )

    def _public_text(self, value: str, redactor: OutputRedactor) -> str:
        return self._bounded(redactor.redact(value)).strip()

    def _run_tests(
        self,
        *,
        project_path: str,
        image: str,
        command: list[str],
        framework: str,
    ) -> dict[str, Any]:
        project = self._resolve_project(project_path)
        snapshot = create_project_snapshot(
            project,
            max_file_bytes=self.settings.max_file_bytes,
            max_project_bytes=self.settings.max_project_bytes,
        )
        redactor = OutputRedactor(
            discover_secret_values(project, snapshot.files)
        )
        container_name = f"cli-agent-test-validator-{uuid.uuid4().hex[:12]}"
        created = False
        verified_policy: dict[str, Any] | None = None
        result_payload: dict[str, Any] | None = None
        try:
            try:
                available = self._docker(
                    ["version", "--format", "{{.Server.Version}}"],
                    timeout=10,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    f"Docker ist nicht verfügbar: {exc}",
                )
                return result_payload
            if available.returncode != 0:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    available.stderr or available.stdout,
                )
                return result_payload

            try:
                created_result = self._create_container(container_name, image)
            except subprocess.TimeoutExpired:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    "Docker-Container-Erstellung lief in ein Timeout.",
                )
                return result_payload
            created = created_result.returncode == 0
            if not created:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    created_result.stderr or created_result.stdout,
                )
                return result_payload

            verified_policy = self._verify_container_policy(container_name)

            started = self._docker(
                ["start", container_name],
                timeout=self.settings.setup_timeout_seconds,
            )
            if started.returncode != 0:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    started.stderr or started.stdout,
                    verified_policy=verified_policy,
                )
                return result_payload

            copied = self._docker(
                ["cp", "-", f"{container_name}:/work"],
                timeout=self.settings.setup_timeout_seconds,
                input_bytes=snapshot.archive,
            )
            if copied.returncode != 0:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    copied.stderr or copied.stdout,
                    verified_policy=verified_policy,
                )
                return result_payload

            try:
                tested = self._docker(
                    [
                        "exec",
                        "--user",
                        "65532:65532",
                        "--workdir",
                        "/work",
                        "--env",
                        "HOME=/tmp/home",
                        container_name,
                        *command,
                    ],
                    timeout=self.settings.test_timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    (
                        "Testlauf nach "
                        f"{self.settings.test_timeout_seconds} Sekunden abgebrochen."
                    ),
                    verified_policy=verified_policy,
                    timed_out=True,
                )
                return result_payload

            output = "\n".join(
                part for part in (tested.stdout, tested.stderr) if part
            )
            result_payload = {
                "success": tested.returncode == 0,
                "framework": framework,
                "project_path": project_path,
                "exit_code": tested.returncode,
                "timed_out": False,
                "output": self._public_text(output, redactor),
                "snapshot": {
                    "file_count": len(snapshot.files),
                    "total_bytes": snapshot.total_bytes,
                    "transport": "in-memory-tar",
                    "host_bind_mount": False,
                },
                "sandbox_policy": {
                    "verified": True,
                    **(verified_policy or {}),
                    "network_mode": "none",
                    "container_user": "65532:65532",
                    "root_filesystem": "read-only",
                },
            }
            return result_payload
        finally:
            removed: bool | None = None
            if created:
                try:
                    cleanup = self._docker(
                        ["rm", "--force", container_name],
                        timeout=20,
                    )
                    removed = cleanup.returncode == 0
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    removed = False
            if result_payload is not None:
                result_payload["container_removed"] = removed

    def _failure(
        self,
        framework: str,
        project_path: str,
        redactor: OutputRedactor,
        detail: str,
        *,
        verified_policy: dict[str, Any] | None = None,
        timed_out: bool = False,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "framework": framework,
            "project_path": project_path,
            "exit_code": None,
            "timed_out": timed_out,
            "output": self._public_text(detail, redactor),
            "sandbox_policy": {
                "verified": verified_policy is not None,
                **(verified_policy or {}),
                "network_mode": "none",
            },
        }

    def run_python_tests(
        self,
        project_path: str = ".",
        test_selector: str | None = None,
    ) -> dict[str, Any]:
        selector = self._validate_selector(test_selector, java=False)
        command = ["python", "-m", "pytest", "-q"]
        if selector:
            command.append(selector)
        return self._run_tests(
            project_path=project_path,
            image=self.settings.python_image,
            command=command,
            framework="pytest",
        )

    def run_java_tests(
        self,
        project_path: str = ".",
        test_selector: str | None = None,
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> dict[str, Any]:
        project = self._resolve_project(project_path)
        if build_system not in {"auto", "maven", "gradle"}:
            raise TestValidationError(
                "build_system muss 'auto', 'maven' oder 'gradle' sein."
            )
        selected = self._detect_java_build_system(project, build_system)
        selector = self._validate_selector(test_selector, java=True)
        if selected == "maven":
            command = ["mvn", "-o", "-B"]
            if selector:
                command.append(f"-Dtest={selector}")
            command.append("test")
            image = self.settings.maven_image
            framework = "maven"
        else:
            command = ["gradle", "--offline", "--no-daemon", "test"]
            if selector:
                command.extend(["--tests", selector])
            image = self.settings.gradle_image
            framework = "gradle"
        return self._run_tests(
            project_path=project_path,
            image=image,
            command=command,
            framework=framework,
        )
