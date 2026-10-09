from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import uuid
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Literal

from .docker_backend import DockerBackend, DockerCommandResult
from .gradle_cache import gradle_cache_entry, validate_gradle_cache_tree
from .maven_cache import cache_entry, validate_repository_tree
from .python_cache import (
    python_cache_entry,
    python_dependency_plan,
    validate_python_cache_tree,
)
from .code_validator_redaction import (
    OutputRedactor,
    SecretDiscoveryLimitError,
    discover_secret_values,
)
from .code_validator_snapshot import create_project_snapshot
from .code_validator_types import CodeValidationError, CodeValidatorSettings

_JAVA_SELECTOR = re.compile(r"^[A-Za-z0-9_.$*#\[\],-]+$")
_MAX_SELECTOR_CHARS = 512
_GRADLE_MIN_SELECTOR_VERSION = (8, 3)
_GRADLE_VERSION_RE = re.compile(r"(?m)^Gradle\s+(\d+)\.(\d+)(?:\.(\d+))?")

class DockerCodeValidator:
    """Run fixed Python or Java test commands in a hardened short-lived container."""

    def __init__(
        self,
        workspace: Path,
        settings: CodeValidatorSettings,
        *,
        backend: DockerBackend | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise CodeValidationError(
                f"Projekt-Workspace existiert nicht: {self.workspace}"
            )
        self.settings = settings
        self.backend = backend or DockerBackend()

    def _resolve_project(self, project_path: str) -> Path:
        if not isinstance(project_path, str) or not project_path.strip():
            raise CodeValidationError("Der Projektpfad darf nicht leer sein.")
        candidate = Path(project_path)
        windows = PureWindowsPath(project_path)
        if candidate.is_absolute() or windows.is_absolute() or windows.drive:
            raise CodeValidationError(
                "Der Projektpfad muss relativ zum Workspace sein."
            )
        if ".." in PurePath(project_path).parts or ".." in windows.parts:
            raise CodeValidationError(
                "Der Projektpfad darf '..' nicht enthalten."
            )
        resolved = (self.workspace / candidate).resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise CodeValidationError(
                "Der Projektpfad verweist außerhalb des Workspaces."
            ) from exc
        if not resolved.is_dir():
            raise CodeValidationError(
                f"Projekt existiert nicht: {project_path!r}"
            )
        return resolved

    @staticmethod
    def _validate_selector(selector: str | None, *, java: bool) -> str | None:
        if selector is None:
            return None
        if not isinstance(selector, str):
            raise CodeValidationError("Der Test-Selector muss ein String sein.")
        value = selector.strip()
        if not value:
            raise CodeValidationError("Der Test-Selector darf nicht leer sein.")
        if len(value) > _MAX_SELECTOR_CHARS:
            raise CodeValidationError("Der Test-Selector ist zu lang.")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise CodeValidationError(
                "Der Test-Selector darf keine Steuerzeichen enthalten."
            )
        if java:
            if value.startswith("-"):
                raise CodeValidationError(
                    "Java-Test-Selectoren dürfen keine Build-Tool-Optionen sein."
                )
            if not _JAVA_SELECTOR.fullmatch(value):
                raise CodeValidationError("Ungültiger Java-Test-Selector.")
            return value
        if value.startswith(("-", "@")):
            raise CodeValidationError(
                "Python-Test-Selectoren dürfen keine pytest-Optionen oder "
                "Argument-Dateien sein."
            )
        path_part = value.split("::", 1)[0]
        path_candidate = PurePath(path_part)
        windows_path = PureWindowsPath(path_part)
        if (
            path_candidate.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or ".." in path_candidate.parts
            or ".." in windows_path.parts
        ):
            raise CodeValidationError(
                "Python-Test-Selector muss innerhalb des Projekts liegen."
            )
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
                raise CodeValidationError(
                    "build_system='maven' benötigt eine pom.xml."
                )
            return "maven"
        if requested == "gradle":
            if not has_gradle:
                raise CodeValidationError(
                    "build_system='gradle' benötigt build.gradle oder build.gradle.kts."
                )
            return "gradle"
        if has_maven and has_gradle:
            raise CodeValidationError(
                "Java-Buildsystem ist mehrdeutig; setze build_system auf "
                "'maven' oder 'gradle'."
            )
        if has_maven:
            return "maven"
        if has_gradle:
            return "gradle"
        raise CodeValidationError(
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
                "--tmpfs",
                (
                    "/output:rw,nosuid,nodev,"
                    f"size={max(1_048_576, self.settings.max_output_chars * 4 + 65_536)},"
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
                "mkdir -p /tmp/home; while :; do sleep 3600; done",
            ],
            timeout=self.settings.setup_timeout_seconds,
        )

    def _verify_container_policy(self, name: str) -> dict[str, Any]:
        result = self._docker(
            ["inspect", name],
            timeout=self.settings.setup_timeout_seconds,
        )
        if result.returncode != 0:
            raise CodeValidationError("Docker-Sandbox konnte nicht geprüft werden.")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CodeValidationError(
                "Docker-Sandbox lieferte ungültige Inspect-Daten."
            ) from exc
        if not isinstance(payload, list) or len(payload) != 1:
            raise CodeValidationError(
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
            "capabilities_dropped": any(
                str(value).casefold() == "all" for value in cap_drop
            ),
            "no_new_privileges": any(
                str(value).startswith("no-new-privileges")
                for value in security_opt
            ),
            "not_privileged": host.get("Privileged") is False,
            "no_host_namespaces": (
                host.get("PidMode") != "host"
                and host.get("IpcMode") != "host"
                and host.get("UTSMode") != "host"
            ),
            "no_host_binds": not bool(host.get("Binds")),
            "no_image_volumes": not bool(config.get("Volumes")),
            "only_expected_mounts": all(
                isinstance(mount, dict)
                and mount.get("Type") == "tmpfs"
                and mount.get("Destination") in {"/tmp", "/work", "/output"}
                for mount in mounts
            ),
            "tmpfs_work": "/work" in tmpfs,
            "tmpfs_tmp": "/tmp" in tmpfs,
            "tmpfs_output": "/output" in tmpfs,
        }
        if not all(checks.values()):
            failed = ", ".join(
                name for name, success in checks.items() if not success
            )
            raise CodeValidationError(
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

    @staticmethod
    def _dependency_refresh_message(framework: str, output: str) -> str | None:
        value = output.casefold()
        patterns: dict[str, tuple[str, ...]] = {
            "maven": (
                "could not resolve dependencies",
                "could not find artifact",
                "was not cached in the local repository",
                "cannot access",
                "plugin or one of its dependencies could not be resolved",
            ),
            "gradle": (
                "no cached version",
                "could not resolve all files",
                "could not resolve",
                "could not find",
                "offline mode",
            ),
            "pytest": (
                "modulenotfounderror",
                "no module named",
                "distributionnotfound",
            ),
        }
        if not any(pattern in value for pattern in patterns.get(framework, ())):
            return None
        command = {
            "maven": "cli-agent-dependency-cache prepare-maven <projekt>",
            "gradle": "cli-agent-dependency-cache prepare-gradle <projekt>",
            "pytest": "cli-agent-dependency-cache prepare-python <projekt>",
        }[framework]
        return (
            "Der vorbereitete Dependency-Cache könnte für den aktuellen "
            "Projektstand unvollständig oder veraltet sein. Führe außerhalb "
            f"des Agents '{command}' aus und wiederhole den Vorgang."
        )


    def _run_tests(
        self,
        *,
        project_path: str,
        image: str,
        command: list[str],
        framework: str,
        pre_test_command: list[str] | None = None,
        dependency_repository: Path | None = None,
        dependency_cache_key: str | None = None,
        python_wheels: Path | None = None,
        gradle_home: Path | None = None,
    ) -> dict[str, Any]:
        project = self._resolve_project(project_path)
        snapshot = create_project_snapshot(
            project,
            max_file_bytes=self.settings.max_file_bytes,
            max_project_bytes=self.settings.max_project_bytes,
            max_snapshot_entries=self.settings.max_snapshot_entries,
        )
        try:
            discovered_secrets = discover_secret_values(
                snapshot.archive,
                max_file_bytes=self.settings.max_file_bytes,
            )
            redactor = OutputRedactor(discovered_secrets)
        except SecretDiscoveryLimitError:
            # Project configuration remains available inside the no-network
            # sandbox, but output is fail-closed if bounded secret discovery
            # cannot safely enumerate all candidate values.
            redactor = OutputRedactor(suppress_output=True)
        container_name = f"cli-agent-code-validator-{uuid.uuid4().hex[:12]}"
        created = False
        create_may_have_succeeded = False
        verified_policy: dict[str, Any] | None = None
        result_payload: dict[str, Any] | None = None
        try:
            try:
                available = self._docker(
                    ["version", "--format", "{{.Server.Version}}"],
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    "Docker-Verfügbarkeitsprüfung lief in ein Timeout.",
                    timed_out=True,
                )
                return result_payload
            except FileNotFoundError as exc:
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
                create_may_have_succeeded = True
                result_payload = self._failure(
                    framework,
                    project_path,
                    redactor,
                    "Docker-Container-Erstellung lief in ein Timeout.",
                    timed_out=True,
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
                [
                    "exec",
                    "--interactive",
                    "--user",
                    "65532:65532",
                    "--workdir",
                    "/work",
                    container_name,
                    "tar",
                    "-xf",
                    "-",
                ],
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

            if python_wheels is not None:
                validate_python_cache_tree(python_wheels)
                prepared_python_dir = self._docker(
                    [
                        "exec",
                        "--user",
                        "65532:65532",
                        container_name,
                        "mkdir",
                        "-p",
                        "/tmp/python-wheels",
                        "/tmp/python-deps",
                    ],
                    timeout=self.settings.setup_timeout_seconds,
                )
                if prepared_python_dir.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        prepared_python_dir.stderr or prepared_python_dir.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload
                try:
                    streamed_python = self.backend.stream_tar_directory(
                        python_wheels,
                        [
                            "exec",
                            "--interactive",
                            "--user",
                            "65532:65532",
                            "--workdir",
                            "/tmp/python-wheels",
                            container_name,
                            "tar",
                            "-xf",
                            "-",
                        ],
                        timeout=self.settings.setup_timeout_seconds,
                    )
                except subprocess.TimeoutExpired:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        "Python-Wheel-Cache-Übertragung lief in ein Timeout.",
                        verified_policy=verified_policy,
                        timed_out=True,
                    )
                    return result_payload
                except (FileNotFoundError, OSError, ValueError) as exc:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        f"Python-Wheel-Cache konnte nicht übertragen werden: {exc}",
                        verified_policy=verified_policy,
                    )
                    return result_payload
                if streamed_python.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        streamed_python.stderr or streamed_python.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload

            if gradle_home is not None:
                validate_gradle_cache_tree(gradle_home)
                prepared_gradle_dir = self._docker(
                    [
                        "exec",
                        "--user",
                        "65532:65532",
                        container_name,
                        "mkdir",
                        "-p",
                        "/tmp/gradle",
                    ],
                    timeout=self.settings.setup_timeout_seconds,
                )
                if prepared_gradle_dir.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        prepared_gradle_dir.stderr or prepared_gradle_dir.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload
                try:
                    streamed_gradle = self.backend.stream_tar_directory(
                        gradle_home,
                        [
                            "exec",
                            "--interactive",
                            "--user",
                            "65532:65532",
                            "--workdir",
                            "/tmp/gradle",
                            container_name,
                            "tar",
                            "-xf",
                            "-",
                        ],
                        timeout=self.settings.setup_timeout_seconds,
                    )
                except subprocess.TimeoutExpired:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        "Gradle-Dependency-Cache-Übertragung lief in ein Timeout.",
                        verified_policy=verified_policy,
                        timed_out=True,
                    )
                    return result_payload
                except (FileNotFoundError, OSError, ValueError) as exc:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        f"Gradle-Dependency-Cache konnte nicht übertragen werden: {exc}",
                        verified_policy=verified_policy,
                    )
                    return result_payload
                if streamed_gradle.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        streamed_gradle.stderr or streamed_gradle.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload

            if dependency_repository is not None:
                validate_repository_tree(dependency_repository)
                prepared_dir = self._docker(
                    [
                        "exec",
                        "--user",
                        "65532:65532",
                        container_name,
                        "mkdir",
                        "-p",
                        "/tmp/m2",
                    ],
                    timeout=self.settings.setup_timeout_seconds,
                )
                if prepared_dir.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        prepared_dir.stderr or prepared_dir.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload
                try:
                    streamed = self.backend.stream_tar_directory(
                        dependency_repository,
                        [
                            "exec",
                            "--interactive",
                            "--user",
                            "65532:65532",
                            "--workdir",
                            "/tmp/m2",
                            container_name,
                            "tar",
                            "-xf",
                            "-",
                        ],
                        timeout=self.settings.setup_timeout_seconds,
                    )
                except subprocess.TimeoutExpired:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        "Maven-Dependency-Cache-Übertragung lief in ein Timeout.",
                        verified_policy=verified_policy,
                        timed_out=True,
                    )
                    return result_payload
                except (FileNotFoundError, OSError, ValueError) as exc:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        f"Maven-Dependency-Cache konnte nicht übertragen werden: {exc}",
                        verified_policy=verified_policy,
                    )
                    return result_payload
                if streamed.returncode != 0:
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        streamed.stderr or streamed.stdout,
                        verified_policy=verified_policy,
                    )
                    return result_payload

            if pre_test_command:
                prepared = self._docker(
                    [
                        "exec",
                        "--user",
                        "65532:65532",
                        "--workdir",
                        "/work",
                        "--env",
                        "HOME=/tmp/home",
                        container_name,
                        *pre_test_command,
                    ],
                    timeout=self.settings.setup_timeout_seconds,
                )
                if prepared.returncode != 0:
                    detail = prepared.stderr or prepared.stdout
                    result_payload = self._failure(
                        framework,
                        project_path,
                        redactor,
                        detail,
                        verified_policy=verified_policy,
                    )
                    refresh_message = (
                        self._dependency_refresh_message(framework, detail)
                        if python_wheels is not None
                        else None
                    )
                    if refresh_message is not None:
                        result_payload["reason"] = "dependency_cache_may_be_stale"
                        result_payload["message_to_user"] = refresh_message
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
                        "--env",
                        "PYTHONPATH=/tmp/python-deps:/work:/work/src",
                        container_name,
                        "sh",
                        "-c",
                        'exec "$@" > /output/test.log 2>&1',
                        "cli-agent-test-command",
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

            captured = self._docker(
                [
                    "exec",
                    "--user",
                    "65532:65532",
                    container_name,
                    "cat",
                    "/output/test.log",
                ],
                timeout=min(30, self.settings.setup_timeout_seconds),
            )
            output = (
                captured.stdout
                if captured.returncode == 0
                else "\n".join(
                    part
                    for part in (
                        tested.stdout,
                        tested.stderr,
                        captured.stderr,
                    )
                    if part
                )
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
                    "transport": "in-memory-tar-via-docker-exec",
                    "host_bind_mount": False,
                },
                "dependency_cache": (
                    {
                        "key": dependency_cache_key,
                        "source": "prepared-host-cache",
                    }
                    if dependency_repository is not None
                    else (
                        {
                            "key": dependency_cache_key,
                            "source": "prepared-gradle-cache",
                        }
                        if gradle_home is not None
                        else (
                            {
                                "key": dependency_cache_key,
                                "source": "prepared-wsl-wheel-cache",
                            }
                            if python_wheels is not None
                            else None
                        )
                    )
                ),
                "sandbox_policy": {
                    "verified": True,
                    **(verified_policy or {}),
                    "network_mode": "none",
                    "container_user": "65532:65532",
                    "root_filesystem": "read-only",
                },
            }
            if tested.returncode != 0 and (
                dependency_repository is not None
                or gradle_home is not None
                or python_wheels is not None
            ):
                refresh_message = self._dependency_refresh_message(
                    framework,
                    output,
                )
                if refresh_message is not None:
                    result_payload["reason"] = "dependency_cache_may_be_stale"
                    result_payload["message"] = (
                        "Die Validierung kann mit dem aktuellen vorbereiteten "
                        "Dependency-Cache nicht zuverlässig abgeschlossen werden, "
                        "weil benötigte Dependencies fehlen oder der Cache "
                        "unvollständig bzw. veraltet ist."
                    )
                    result_payload["message_to_user"] = refresh_message
            return result_payload
        except subprocess.TimeoutExpired:
            result_payload = self._failure(
                framework,
                project_path,
                redactor,
                (
                    "Docker-Sandbox-Setup oder -Übertragung lief nach "
                    f"{self.settings.setup_timeout_seconds} Sekunden in ein Timeout."
                ),
                verified_policy=verified_policy,
                timed_out=True,
            )
            return result_payload
        finally:
            removed: bool | None = None
            if created or create_may_have_succeeded:
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
        project = self._resolve_project(project_path)
        selector = self._validate_selector(test_selector, java=False)
        command = ["python", "-m", "pytest", "-q"]
        if selector:
            command.append(selector)

        python_wheels: Path | None = None
        dependency_cache_key: str | None = None
        pre_test_command: list[str] | None = None
        plan = python_dependency_plan(
            project,
            max_file_bytes=self.settings.max_file_bytes,
        )
        if plan.has_dependencies and self.settings.python_cache_root is not None:
            entry = python_cache_entry(
                self.settings.python_cache_root,
                project,
                max_file_bytes=self.settings.max_file_bytes,
            )
            dependency_cache_key = entry.key
            if not entry.is_ready():
                return {
                    "success": False,
                    "framework": "pytest",
                    "project_path": project_path,
                    "reason": "dependencies_not_prepared",
                    "dependency_cache_key": entry.key,
                    "message": (
                        "Die Python-Validierung kann nicht ausgeführt werden, "
                        "weil der benötigte vorbereitete Linux-Wheel-Cache fehlt."
                    ),
                    "message_to_user": (
                        "Python-Dependencies sind noch nicht vorbereitet. Führe "
                        "unter WSL 'cli-agent-dependency-cache prepare-python <projekt>' "
                        "aus und wiederhole den Test."
                    ),
                    "preparation_environment": "WSL required",
                }
            python_wheels = entry.wheels
            wheel_names = entry.install_wheel_names()
            if wheel_names:
                install = [
                    "python",
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-index",
                    "--target",
                    "/tmp/python-deps",
                    *[
                        f"/tmp/python-wheels/{wheel_name}"
                        for wheel_name in wheel_names
                    ],
                ]
                pre_test_command = install

        return self._run_tests(
            project_path=project_path,
            image=self.settings.python_image,
            command=command,
            framework="pytest",
            pre_test_command=pre_test_command,
            dependency_cache_key=dependency_cache_key,
            python_wheels=python_wheels,
        )

    def run_java_tests(
        self,
        project_path: str = ".",
        test_selector: str | None = None,
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> dict[str, Any]:
        project = self._resolve_project(project_path)
        if build_system not in {"auto", "maven", "gradle"}:
            raise CodeValidationError(
                "build_system muss 'auto', 'maven' oder 'gradle' sein."
            )
        selected = self._detect_java_build_system(project, build_system)
        selector = self._validate_selector(test_selector, java=True)
        dependency_repository: Path | None = None
        dependency_cache_key: str | None = None
        gradle_home: Path | None = None
        pre_test_command: list[str] | None = None
        if selected == "maven":
            command = [
                "mvn",
                "-o",
                "-B",
                "-Dmaven.repo.local=/tmp/m2",
            ]
            if selector:
                command.append(f"-Dtest={selector}")
            command.append("test")
            if self.settings.maven_cache_root is not None:
                entry = cache_entry(self.settings.maven_cache_root, project)
                dependency_cache_key = entry.key
                if not entry.is_ready():
                    return {
                        "success": False,
                        "framework": "maven",
                        "project_path": project_path,
                        "reason": "dependencies_not_prepared",
                        "dependency_cache_key": entry.key,
                        "message": (
                            "Die Maven-Validierung kann nicht ausgeführt werden, "
                            "weil der benötigte vorbereitete Offline-Cache fehlt."
                        ),
                        "message_to_user": (
                            "Maven-Dependencies sind noch nicht vorbereitet. Führe "
                            "außerhalb des Agents 'cli-agent-dependency-cache prepare-maven "
                            "<projekt>' aus und wiederhole den Test."
                        ),
                    }
                dependency_repository = entry.repository
                pre_test_command = None
            image = self.settings.maven_image
            framework = "maven"
        else:
            command = [
                "gradle",
                "--offline",
                "--no-daemon",
                "--gradle-user-home",
                "/tmp/gradle",
            ]
            command.append("test")
            if selector:
                gradle_selector = selector.replace("#", ".", 1)
                command.extend(["--tests", gradle_selector])
            gradle_home: Path | None = None
            if self.settings.gradle_cache_root is not None:
                entry = gradle_cache_entry(self.settings.gradle_cache_root, project)
                dependency_cache_key = entry.key
                if not entry.is_ready():
                    return {
                        "success": False,
                        "framework": "gradle",
                        "project_path": project_path,
                        "reason": "dependencies_not_prepared",
                        "dependency_cache_key": entry.key,
                        "message": (
                            "Die Gradle-Validierung kann nicht ausgeführt werden, "
                            "weil der benötigte vorbereitete Offline-Cache fehlt."
                        ),
                        "message_to_user": (
                            "Gradle-Dependencies sind noch nicht vorbereitet. Führe "
                            "außerhalb des Agents 'cli-agent-dependency-cache prepare-gradle "
                            "<projekt>' aus und wiederhole den Test."
                        ),
                    }
                gradle_home = entry.gradle_home
            image = self.settings.gradle_image
            framework = "gradle"
        return self._run_tests(
            project_path=project_path,
            image=image,
            command=command,
            framework=framework,
            pre_test_command=pre_test_command,
            dependency_repository=dependency_repository,
            dependency_cache_key=dependency_cache_key,
            gradle_home=gradle_home,
        )

    def run_java_build(
        self,
        project_path: str = ".",
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> dict[str, Any]:
        """Run the fixed Maven package or Gradle assemble validation command."""

        project = self._resolve_project(project_path)
        if build_system not in {"auto", "maven", "gradle"}:
            raise CodeValidationError(
                "build_system muss 'auto', 'maven' oder 'gradle' sein."
            )
        selected = self._detect_java_build_system(project, build_system)
        if selected == "maven":
            return self.run_maven_build(project_path)
        return self.run_gradle_build(project_path)

    def run_maven_build(
        self,
        project_path: str = ".",
    ) -> dict[str, Any]:
        """Build/package a Maven project offline without executing tests."""
        project = self._resolve_project(project_path)
        if not (project / "pom.xml").is_file():
            raise CodeValidationError(
                "run_maven_build benötigt eine pom.xml."
            )

        command = [
            "mvn",
            "-o",
            "-B",
            "-Dmaven.repo.local=/tmp/m2",
            "-DskipTests",
            "package",
        ]
        dependency_repository: Path | None = None
        dependency_cache_key: str | None = None
        pre_test_command: list[str] | None = None
        if self.settings.maven_cache_root is not None:
            entry = cache_entry(self.settings.maven_cache_root, project)
            dependency_cache_key = entry.key
            if not entry.is_ready():
                return {
                    "success": False,
                    "framework": "maven",
                    "operation": "build",
                    "project_path": project_path,
                    "reason": "dependencies_not_prepared",
                    "dependency_cache_key": entry.key,
                    "message": (
                        "Der Maven-Build kann nicht ausgeführt werden, weil der "
                        "benötigte vorbereitete Offline-Cache fehlt."
                    ),
                    "message_to_user": (
                        "Maven-Dependencies sind noch nicht vorbereitet. Führe "
                        "außerhalb des Agents 'cli-agent-dependency-cache prepare-maven "
                        "<projekt>' aus und wiederhole den Build."
                    ),
                }
            dependency_repository = entry.repository

        result = self._run_tests(
            project_path=project_path,
            image=self.settings.maven_image,
            command=command,
            framework="maven",
            pre_test_command=pre_test_command,
            dependency_repository=dependency_repository,
            dependency_cache_key=dependency_cache_key,
        )
        result["operation"] = "build"
        result["tests_executed"] = False
        return result

    def run_gradle_build(
        self,
        project_path: str = ".",
    ) -> dict[str, Any]:
        """Run the fixed Gradle assemble task inside the sandbox."""
        project = self._resolve_project(project_path)
        if not (
            (project / "build.gradle").is_file()
            or (project / "build.gradle.kts").is_file()
        ):
            raise CodeValidationError(
                "run_gradle_build benötigt build.gradle oder build.gradle.kts."
            )

        command = [
            "gradle",
            "--offline",
            "--no-daemon",
            "--gradle-user-home",
            "/tmp/gradle",
            "assemble",
        ]
        gradle_home: Path | None = None
        dependency_cache_key: str | None = None
        pre_test_command: list[str] | None = None
        if self.settings.gradle_cache_root is not None:
            entry = gradle_cache_entry(self.settings.gradle_cache_root, project)
            dependency_cache_key = entry.key
            if not entry.is_ready():
                return {
                    "success": False,
                    "framework": "gradle",
                    "operation": "build",
                    "project_path": project_path,
                    "reason": "dependencies_not_prepared",
                    "dependency_cache_key": entry.key,
                    "message": (
                        "Der Gradle-Build kann nicht ausgeführt werden, weil der "
                        "benötigte vorbereitete Offline-Cache fehlt."
                    ),
                    "message_to_user": (
                        "Gradle-Dependencies sind noch nicht vorbereitet. Führe "
                        "außerhalb des Agents 'cli-agent-dependency-cache prepare-gradle "
                        "<projekt>' aus und wiederhole den Build."
                    ),
                }
            gradle_home = entry.gradle_home

        result = self._run_tests(
            project_path=project_path,
            image=self.settings.gradle_image,
            command=command,
            framework="gradle",
            pre_test_command=pre_test_command,
            dependency_cache_key=dependency_cache_key,
            gradle_home=gradle_home,
        )
        result["operation"] = "build"
        result["requested_gradle_task"] = "assemble"
        return result

