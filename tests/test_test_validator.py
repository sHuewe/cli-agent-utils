from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from cli_agent_mcp.docker_backend import (
    DockerBackend,
    DockerCommandResult,
    _open_verified_stream_file,
)
from cli_agent_mcp.filesystem_safety import (
    _is_windows_reparse_point,
    _is_windows_reparse_point as _docker_reparse_point,
)
from cli_agent_mcp.gradle_cache import (
    gradle_cache_entry,
    gradle_dependency_key,
    write_gradle_ready_metadata,
)
from cli_agent_mcp.maven_cache import cache_entry, maven_dependency_key, write_ready_metadata
from cli_agent_mcp.python_cache import (
    python_cache_entry,
    python_dependency_plan,
    write_python_ready_metadata,
)
from cli_agent_mcp.test_validator import DockerTestValidator
from cli_agent_mcp.test_validator_redaction import (
    OutputRedactor,
    SecretDiscoveryLimitError,
    discover_secret_values,
)
from cli_agent_mcp.test_validator_server import _workspace_from_core_environment
from cli_agent_mcp.test_validator_snapshot import (
    _open_verified_regular_file,
    create_project_snapshot,
)
from cli_agent_mcp.test_validator_types import (
    TestValidationError as ValidationError,
    TestValidatorSettings as ValidatorSettings,
)

PINNED_PYTHON = "registry.internal/python-tests@sha256:" + "a" * 64
PINNED_MAVEN = "registry.internal/maven-tests@sha256:" + "b" * 64
PINNED_GRADLE = "registry.internal/gradle-tests@sha256:" + "c" * 64


def settings() -> ValidatorSettings:
    return ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
    )


def inspect_payload() -> str:
    return json.dumps(
        [
            {
                "Config": {"User": "65532:65532"},
                "HostConfig": {
                    "NetworkMode": "none",
                    "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "Privileged": False,
                    "Binds": None,
                    "Tmpfs": {
                        "/tmp": "rw,nosuid,nodev",
                        "/work": "rw,nosuid,nodev",
                        "/output": "rw,nosuid,nodev",
                    },
                },
                "Mounts": [
                    {"Type": "tmpfs", "Destination": "/tmp"},
                    {"Type": "tmpfs", "Destination": "/work"},
                    {"Type": "tmpfs", "Destination": "/output"},
                ],
            }
        ]
    )


class FakeBackend:
    def __init__(self, exec_output: str = "tests passed") -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []
        self.exec_output = exec_output

    def run(
        self,
        arguments,
        *,
        timeout,
        input_bytes=None,
    ) -> DockerCommandResult:
        args = list(arguments)
        self.calls.append((args, input_bytes))
        command = args[0]
        if command == "inspect":
            return DockerCommandResult(0, inspect_payload(), "")
        if command == "exec":
            return DockerCommandResult(0, self.exec_output, "")
        return DockerCommandResult(0, "ok", "")

    def stream_tar_directory(
        self,
        source,
        arguments,
        *,
        timeout,
    ) -> DockerCommandResult:
        args = list(arguments)
        self.calls.append((["stream-tar", str(source), *args], None))
        return DockerCommandResult(0, "ok", "")


def test_docker_backend_builds_native_and_wsl_commands() -> None:
    native = DockerBackend()
    wsl = DockerBackend(wsl=True, wsl_distribution="Ubuntu")

    assert native.command("version") == ["docker", "version"]
    assert wsl.command("version") == [
        "wsl",
        "-d",
        "Ubuntu",
        "--",
        "docker",
        "version",
    ]


def test_snapshot_keeps_project_env_but_omits_agent_and_build_state(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("API_TOKEN=secret-value\n", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".cli-agent").mkdir()
    (tmp_path / ".cli-agent" / "dump.txt").write_text("private", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "old.class").write_bytes(b"x")

    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    relative = {path.relative_to(tmp_path).as_posix() for path in snapshot.files}
    assert ".env" in relative
    assert "src.py" in relative
    assert ".cli-agent/dump.txt" not in relative
    assert "target/old.class" not in relative
    assert snapshot.archive




def test_snapshot_keeps_nested_source_directory_named_build(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "main" / "java" / "com" / "example" / "build"
    nested.mkdir(parents=True)
    source = nested / "GeneratedLikeName.java"
    source.write_text("class GeneratedLikeName {}\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.class").write_bytes(b"x")

    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    relative = {path.relative_to(tmp_path).as_posix() for path in snapshot.files}
    assert "src/main/java/com/example/build/GeneratedLikeName.java" in relative
    assert "build/generated.class" not in relative


def test_snapshot_rejects_symlink_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(ValidationError, match="Symlinks"):
        create_project_snapshot(
            tmp_path,
            max_file_bytes=1024 * 1024,
            max_project_bytes=4 * 1024 * 1024,
        )


def test_generic_redaction_removes_short_values_without_marker_echo() -> None:
    redactor = OutputRedactor()

    result = redactor.redact("password=x\nAuthorization: Bearer y")

    assert "password=x" not in result
    assert "Bearer y" not in result
    assert result == "password=\nAuthorization: Bearer "


def test_generic_redaction_removes_short_values_without_marker_echo() -> None:
    redactor = OutputRedactor()

    result = redactor.redact("password=x\nAuthorization: Bearer y")

    assert "password=x" not in result
    assert "Bearer y" not in result
    assert result == "password=\nAuthorization: Bearer "


def test_output_redactor_removes_known_and_generic_secrets() -> None:
    redactor = OutputRedactor(["super-secret-value"])

    text = redactor.redact(
        "value=super-secret-value\nAuthorization: Bearer abcdef\npassword=hunter2"
    )

    assert "super-secret-value" not in text
    assert "abcdef" not in text
    assert "hunter2" not in text
    assert "⟦x⟧" in text


def test_python_requirements_respect_validator_file_size_limit(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "demo-package==1.0\n" * 100,
        encoding="utf-8",
    )
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        max_file_bytes=64,
    )
    validator = DockerTestValidator(
        tmp_path,
        configured,
        backend=FakeBackend(),
    )

    with pytest.raises(ValidationError, match="Größenlimit"):
        validator.run_python_tests(".")


def test_python_tests_use_fixed_no_shell_command_and_redact_output(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# no external dependencies\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "API_TOKEN=super-secret-value\n",
        encoding="utf-8",
    )
    (tmp_path / "test_demo.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    backend = FakeBackend(
        exec_output=(
            "Traceback (most recent call last):\n"
            '  File "/work/app.py", line 42, in run\n'
            "    raise RuntimeError('boom')\n"
            "RuntimeError: boom\n"
            "token=super-secret-value\n"
        )
    )
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_python_tests(".", "test_demo.py::test_ok")

    assert result["success"] is True
    assert result["container_removed"] is True
    assert "super-secret-value" not in result["output"]
    assert "Traceback (most recent call last):" in result["output"]
    assert 'File "/work/app.py", line 42, in run' in result["output"]
    assert "RuntimeError: boom" in result["output"]
    exec_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "python" in args
    )
    assert exec_call[-5:] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "test_demo.py::test_ok",
    ]
    create_call = next(args for args, _ in backend.calls if args[0] == "create")
    assert create_call[create_call.index("--network") + 1] == "none"
    assert "--read-only" in create_call
    assert any(value.startswith("/output:") for value in create_call)
    assert ["--cap-drop", "ALL"] == create_call[
        create_call.index("--cap-drop") : create_call.index("--cap-drop") + 2
    ]
    snapshot_transfer = next(
        (args, payload)
        for args, payload in backend.calls
        if args[0] == "exec" and payload is not None
    )
    assert snapshot_transfer[1]
    assert snapshot_transfer[0][-3:] == ["tar", "-xf", "-"]


def test_snapshot_transfer_timeout_returns_structured_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# no external dependencies\n",
        encoding="utf-8",
    )

    class SnapshotTimeoutBackend(FakeBackend):
        def run(self, arguments, *, timeout, input_bytes=None):
            args = list(arguments)
            self.calls.append((args, input_bytes))
            if args[0] == "inspect":
                return DockerCommandResult(0, inspect_payload(), "")
            if args[0] == "exec" and input_bytes is not None:
                raise subprocess.TimeoutExpired(args, timeout)
            return DockerCommandResult(0, "ok", "")

    validator = DockerTestValidator(
        tmp_path,
        settings(),
        backend=SnapshotTimeoutBackend(),
    )

    result = validator.run_python_tests(".")

    assert result["success"] is False
    assert result["timed_out"] is True
    assert "Timeout" in result["output"]
    assert result["container_removed"] is True


def test_java_maven_selector_is_translated_without_shell(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_java_tests(
        ".",
        "com.example.ExampleTest#works",
    )

    assert result["success"] is True
    assert result["framework"] == "maven"
    exec_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "mvn" in args
    )
    assert exec_call[-7:] == [
        "mvn",
        "-o",
        "-B",
        "-Dmaven.repo.local=/tmp/m2",
        "-Dtest=com.example.ExampleTest#works",
        "-Dsurefire.failIfNoSpecifiedTests=false",
        "test",
    ]
    assert not any(
        "/opt/cli-agent-test-cache/maven" in " ".join(args)
        for args, _ in backend.calls
    )


def test_java_auto_detection_rejects_ambiguous_project(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    validator = DockerTestValidator(tmp_path, settings(), backend=FakeBackend())

    with pytest.raises(ValidationError, match="mehrdeutig"):
        validator.run_java_tests(".")


def test_workspace_is_taken_only_from_core_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLI_AGENT_WORKSPACE_ACCESS", "read")
    monkeypatch.setenv("CLI_AGENT_WORKSPACE_DIRECTORY", str(tmp_path))

    assert _workspace_from_core_environment() == tmp_path


def test_workspace_environment_requires_read_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLI_AGENT_WORKSPACE_ACCESS", "none")
    monkeypatch.setenv("CLI_AGENT_WORKSPACE_DIRECTORY", str(tmp_path))

    with pytest.raises(ValidationError, match="Read-Zugriff"):
        _workspace_from_core_environment()


def test_validator_settings_require_pinned_images() -> None:
    with pytest.raises(ValueError, match="sha256"):
        ValidatorSettings(
            python_image="python:latest",
            maven_image=PINNED_MAVEN,
            gradle_image=PINNED_GRADLE,
        )


def test_python_selector_cannot_be_used_as_pytest_option(tmp_path: Path) -> None:
    validator = DockerTestValidator(tmp_path, settings(), backend=FakeBackend())

    with pytest.raises(ValidationError, match="pytest-Optionen"):
        validator.run_python_tests(".", "--collect-only")


def test_gradle_uses_offline_tmpfs_cache_seed(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_java_tests(
        ".",
        "com.example.ExampleTest#works",
        build_system="gradle",
    )

    assert result["success"] is True
    test_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "gradle" in args
    )
    assert test_call[-8:] == [
        "gradle",
        "--offline",
        "--no-daemon",
        "--gradle-user-home",
        "/tmp/gradle",
        "test",
        "--tests",
        "com.example.ExampleTest.works",
    ]
    assert not any(
        "/opt/cli-agent-test-cache/gradle" in " ".join(args)
        for args, _ in backend.calls
    )


def test_sandbox_verification_rejects_image_declared_volume(tmp_path: Path) -> None:
    class VolumeBackend(FakeBackend):
        def run(self, arguments, *, timeout, input_bytes=None):
            args = list(arguments)
            self.calls.append((args, input_bytes))
            if args[0] == "inspect":
                payload = json.loads(inspect_payload())
                payload[0]["Config"]["Volumes"] = {"/hostish": {}}
                return DockerCommandResult(0, json.dumps(payload), "")
            return DockerCommandResult(0, "ok", "")

    validator = DockerTestValidator(
        tmp_path,
        settings(),
        backend=VolumeBackend(),
    )

    with pytest.raises(ValidationError, match="no_image_volumes"):
        validator._verify_container_policy("container")


def test_maven_cache_key_is_stable_across_pom_changes(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project>A</project>", encoding="utf-8")
    first = maven_dependency_key(tmp_path)

    (tmp_path / "pom.xml").write_text("<project>B</project>", encoding="utf-8")
    second = maven_dependency_key(tmp_path)

    assert first.startswith("maven-")
    assert first == second


def test_maven_dependency_key_ignores_source_changes(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    source = tmp_path / "src" / "main" / "java"
    source.mkdir(parents=True)
    java_file = source / "Example.java"
    java_file.write_text("class Example {}", encoding="utf-8")
    first = maven_dependency_key(tmp_path)

    java_file.write_text("class Example { int x; }", encoding="utf-8")
    second = maven_dependency_key(tmp_path)

    assert first == second


def test_maven_uses_prepared_cache_selected_by_dependency_key(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "dependency-cache"
    entry = cache_entry(cache_root, tmp_path)
    entry.repository.mkdir(parents=True)
    artifact = entry.repository / "com" / "example" / "demo" / "1.0"
    artifact.mkdir(parents=True)
    (artifact / "demo-1.0.jar").write_bytes(b"jar")
    write_ready_metadata(entry.directory, entry.key)

    backend = FakeBackend()
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        maven_cache_root=cache_root,
    )
    validator = DockerTestValidator(tmp_path, configured, backend=backend)

    result = validator.run_java_tests(".", build_system="maven")

    assert result["success"] is True
    assert result["dependency_cache"] == {
        "key": entry.key,
        "source": "prepared-host-cache",
    }
    transfer = next(args for args, _ in backend.calls if args[0] == "stream-tar")
    assert str(entry.repository) in transfer
    assert "/tmp/m2" in transfer


def test_maven_reports_missing_prepared_dependency_cache(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "dependency-cache"
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        maven_cache_root=cache_root,
    )
    validator = DockerTestValidator(tmp_path, configured, backend=FakeBackend())

    result = validator.run_java_tests(".", build_system="maven")

    assert result["success"] is False
    assert result["reason"] == "dependencies_not_prepared"
    assert result["dependency_cache_key"].startswith("maven-")


def test_python_reports_missing_wsl_prepared_dependency_cache(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        python_cache_root=tmp_path / "python-cache",
    )
    validator = DockerTestValidator(tmp_path, configured, backend=FakeBackend())

    result = validator.run_python_tests(".")

    assert result["success"] is False
    assert result["reason"] == "dependencies_not_prepared"
    assert result["preparation_environment"] == "WSL required"
    assert "prepare-python" in result["message_to_user"]


def test_python_uses_wsl_prepared_wheels_offline(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    cache_root = tmp_path / "python-cache"
    entry = python_cache_entry(cache_root, tmp_path)
    entry.wheels.mkdir(parents=True)
    (entry.wheels / "demo_package-1.0-py3-none-any.whl").write_bytes(b"wheel")
    write_python_ready_metadata(
        entry.directory,
        entry.key,
        python_dependency_plan(tmp_path),
    )

    backend = FakeBackend()
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        python_cache_root=cache_root,
    )
    validator = DockerTestValidator(tmp_path, configured, backend=backend)

    result = validator.run_python_tests(".")

    assert result["success"] is True
    assert result["dependency_cache"] == {
        "key": entry.key,
        "source": "prepared-wsl-wheel-cache",
    }
    transfer = next(
        args
        for args, _ in backend.calls
        if args[0] == "stream-tar" and str(entry.wheels) in args
    )
    assert "/tmp/python-wheels" in transfer
    install = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec"
        and "--no-index" in args
        and any(value.startswith("/tmp/python-wheels/") for value in args)
    )
    assert "--target" in install
    assert "/tmp/python-deps" in install
    assert "-r" not in install


def test_gradle_reports_missing_prepared_dependency_cache(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        gradle_cache_root=tmp_path / "gradle-cache",
    )
    validator = DockerTestValidator(tmp_path, configured, backend=FakeBackend())

    result = validator.run_java_tests(".", build_system="gradle")

    assert result["success"] is False
    assert result["reason"] == "dependencies_not_prepared"
    assert result["dependency_cache_key"].startswith("gradle-")


def test_gradle_uses_prepared_cache_offline(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    cache_root = tmp_path / "gradle-cache"
    entry = gradle_cache_entry(cache_root, tmp_path)
    (entry.gradle_home / "caches").mkdir(parents=True)
    (entry.gradle_home / "caches" / "artifact.bin").write_bytes(b"cache")
    write_gradle_ready_metadata(entry.directory, entry.key)

    backend = FakeBackend()
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        gradle_cache_root=cache_root,
    )
    validator = DockerTestValidator(tmp_path, configured, backend=backend)

    result = validator.run_java_tests(".", build_system="gradle")

    assert result["success"] is True
    assert result["dependency_cache"] == {
        "key": entry.key,
        "source": "prepared-gradle-cache",
    }
    transfer = next(
        args
        for args, _ in backend.calls
        if args[0] == "stream-tar" and str(entry.gradle_home) in args
    )
    assert "/tmp/gradle" in transfer
    test_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "gradle" in args
    )
    assert "--offline" in test_call
    assert "--gradle-user-home" in test_call
    assert "/tmp/gradle" in test_call


def test_maven_build_packages_without_running_tests(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_maven_build(".")

    assert result["success"] is True
    assert result["operation"] == "build"
    assert result["tests_executed"] is False
    build_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "mvn" in args
    )
    assert build_call[-6:] == [
        "mvn",
        "-o",
        "-B",
        "-Dmaven.repo.local=/tmp/m2",
        "-DskipTests",
        "package",
    ]


def test_gradle_build_requests_fixed_assemble_task(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_gradle_build(".")

    assert result["success"] is True
    assert result["operation"] == "build"
    assert result["requested_gradle_task"] == "assemble"
    build_call = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "gradle" in args
    )
    assert build_call[-6:] == [
        "gradle",
        "--offline",
        "--no-daemon",
        "--gradle-user-home",
        "/tmp/gradle",
        "assemble",
    ]
    assert "cli-agent-disable-tests.gradle" not in " ".join(build_call)


def test_maven_build_requires_prepared_cache_when_configured(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        maven_cache_root=tmp_path / "maven-cache",
    )
    validator = DockerTestValidator(tmp_path, configured, backend=FakeBackend())

    result = validator.run_maven_build(".")

    assert result["success"] is False
    assert result["operation"] == "build"
    assert result["reason"] == "dependencies_not_prepared"


def test_gradle_build_requires_prepared_cache_when_configured(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        gradle_cache_root=tmp_path / "gradle-cache",
    )
    validator = DockerTestValidator(tmp_path, configured, backend=FakeBackend())

    result = validator.run_gradle_build(".")

    assert result["success"] is False
    assert result["operation"] == "build"
    assert result["reason"] == "dependencies_not_prepared"


def test_java_build_auto_detects_maven(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_java_build(".")

    assert result["success"] is True
    assert result["framework"] == "maven"
    assert result["operation"] == "build"


def test_java_build_auto_detects_gradle(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    backend = FakeBackend()
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_java_build(".")

    assert result["success"] is True
    assert result["framework"] == "gradle"
    assert result["operation"] == "build"


def test_java_build_rejects_ambiguous_project(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    validator = DockerTestValidator(tmp_path, settings(), backend=FakeBackend())

    with pytest.raises(ValidationError, match="mehrdeutig"):
        validator.run_java_build(".")


def test_gradle_dependency_key_changes_with_buildsrc_source(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    buildsrc = tmp_path / "buildSrc" / "src" / "main" / "kotlin"
    buildsrc.mkdir(parents=True)
    source = buildsrc / "Dependencies.kt"
    source.write_text(
        'const val jacksonVersion = "2.20.0"\n',
        encoding="utf-8",
    )

    first = gradle_dependency_key(tmp_path)
    source.write_text(
        'const val jacksonVersion = "2.21.0"\n',
        encoding="utf-8",
    )
    second = gradle_dependency_key(tmp_path)

    assert first.startswith("gradle-")
    assert first == second



def test_gradle_dependency_key_changes_with_custom_version_catalog(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    gradle_dir = tmp_path / "gradle"
    gradle_dir.mkdir()
    catalog = gradle_dir / "test.versions.toml"
    catalog.write_text(
        '[versions]\njunit = "5.11.0"\n',
        encoding="utf-8",
    )

    first = gradle_dependency_key(tmp_path)
    catalog.write_text(
        '[versions]\njunit = "5.12.0"\n',
        encoding="utf-8",
    )
    second = gradle_dependency_key(tmp_path)

    assert first == second






def test_python_empty_manifest_skips_pip_install(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# intentionally empty\n",
        encoding="utf-8",
    )
    cache_root = tmp_path / "python-cache"
    entry = python_cache_entry(cache_root, tmp_path)
    entry.wheels.mkdir(parents=True)
    write_python_ready_metadata(
        entry.directory,
        entry.key,
        python_dependency_plan(tmp_path),
    )

    backend = FakeBackend()
    configured = ValidatorSettings(
        python_image=PINNED_PYTHON,
        maven_image=PINNED_MAVEN,
        gradle_image=PINNED_GRADLE,
        python_cache_root=cache_root,
    )
    validator = DockerTestValidator(tmp_path, configured, backend=backend)

    result = validator.run_python_tests(".")

    assert result["success"] is True
    assert not any(
        args[0] == "exec" and "--no-index" in args
        for args, _ in backend.calls
    )


def test_snapshot_preserves_fixture_suffixes(tmp_path: Path) -> None:
    fixture = tmp_path / "tests" / "fixtures" / "server.log"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("expected log fixture\n", encoding="utf-8")

    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    relative = {path.relative_to(tmp_path).as_posix() for path in snapshot.files}
    assert "tests/fixtures/server.log" in relative



def test_java_selector_cannot_be_build_tool_option(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    validator = DockerTestValidator(tmp_path, settings(), backend=FakeBackend())

    with pytest.raises(ValidationError, match="Build-Tool-Optionen"):
        validator.run_java_tests(
            ".",
            "--version",
            build_system="gradle",
        )



def test_gradle_dependency_key_changes_with_lockfile(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    lockfile = tmp_path / "gradle.lockfile"
    lockfile.write_text("com.example:demo:1.0=runtimeClasspath\n", encoding="utf-8")

    first = gradle_dependency_key(tmp_path)
    lockfile.write_text("com.example:demo:2.0=runtimeClasspath\n", encoding="utf-8")
    second = gradle_dependency_key(tmp_path)

    assert first == second


def test_gradle_dependency_key_changes_with_legacy_lockfile(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    locks = tmp_path / "gradle" / "dependency-locks"
    locks.mkdir(parents=True)
    lockfile = locks / "runtimeClasspath.lockfile"
    lockfile.write_text("com.example:demo:1.0\n", encoding="utf-8")

    first = gradle_dependency_key(tmp_path)
    lockfile.write_text("com.example:demo:2.0\n", encoding="utf-8")
    second = gradle_dependency_key(tmp_path)

    assert first == second



def test_gradle_dependency_key_changes_with_custom_named_toml_catalog(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle.kts").write_text("", encoding="utf-8")
    gradle_dir = tmp_path / "gradle"
    gradle_dir.mkdir()
    catalog = gradle_dir / "catalog.toml"
    catalog.write_text(
        '[versions]\njunit = "5.11.0"\n',
        encoding="utf-8",
    )

    first = gradle_dependency_key(tmp_path)
    catalog.write_text(
        '[versions]\njunit = "5.12.0"\n',
        encoding="utf-8",
    )
    second = gradle_dependency_key(tmp_path)

    assert first == second



def test_gradle_dependency_key_keeps_nested_project_named_build(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    module = tmp_path / "modules" / "build"
    module.mkdir(parents=True)
    build_file = module / "build.gradle"
    build_file.write_text(
        "dependencies { implementation 'com.example:demo:1.0' }\n",
        encoding="utf-8",
    )

    first = gradle_dependency_key(tmp_path)
    build_file.write_text(
        "dependencies { implementation 'com.example:demo:2.0' }\n",
        encoding="utf-8",
    )
    second = gradle_dependency_key(tmp_path)

    assert first == second



def test_maven_cache_key_does_not_parse_reactor_modules(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        """
<project>
  <modelVersion>4.0.0</modelVersion>
  <modules><module>child</module></modules>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert maven_dependency_key(tmp_path).startswith("maven-")


def test_maven_dependency_key_ignores_unrelated_malformed_pom_fixture(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion></project>\n",
        encoding="utf-8",
    )
    fixture = tmp_path / "src" / "test" / "resources" / "broken"
    fixture.mkdir(parents=True)
    (fixture / "pom.xml").write_text("<project>", encoding="utf-8")

    key = maven_dependency_key(tmp_path)

    assert key.startswith("maven-")


def test_gradle_commented_include_build_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    (tmp_path / "settings.gradle").write_text(
        '// includeBuild("../outside-plugin")\n'
        '/* includeBuild("../other-plugin") */\n',
        encoding="utf-8",
    )

    key = gradle_dependency_key(tmp_path)

    assert key.startswith("gradle-")


def test_gradle_include_build_inside_string_is_not_treated_as_comment(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    included = tmp_path / "build-logic"
    included.mkdir()
    (included / "build.gradle").write_text("", encoding="utf-8")
    (tmp_path / "settings.gradle").write_text(
        'includeBuild("build-logic")\n',
        encoding="utf-8",
    )

    key = gradle_dependency_key(tmp_path)

    assert key.startswith("gradle-")



def test_windows_reparse_point_detection() -> None:
    class FakeStat:
        st_file_attributes = 0x0400

    assert _is_windows_reparse_point(FakeStat()) is True



def test_docker_stream_reparse_point_detection() -> None:
    class FakeStat:
        st_file_attributes = 0x0400

    assert _docker_reparse_point(FakeStat()) is True



def test_maven_cache_key_does_not_parse_local_parent_pom(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0</version>
    <relativePath>parent.xml</relativePath>
  </parent>
  <artifactId>child</artifactId>
</project>
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert maven_dependency_key(tmp_path).startswith("maven-")



def test_gradle_offline_dependency_failure_requests_cache_refresh(
    tmp_path: Path,
) -> None:
    (tmp_path / "build.gradle").write_text("", encoding="utf-8")
    cache_root = tmp_path / "gradle-cache"
    entry = gradle_cache_entry(cache_root, tmp_path)
    (entry.gradle_home / "caches").mkdir(parents=True)
    write_gradle_ready_metadata(entry.directory, entry.key)

    class MissingDependencyBackend(FakeBackend):
        def run(self, arguments, *, timeout, input_bytes=None):
            args = list(arguments)
            self.calls.append((args, input_bytes))
            if args[0] == "inspect":
                return DockerCommandResult(0, inspect_payload(), "")
            if args[0] == "exec" and "cat" in args:
                return DockerCommandResult(
                    0,
                    "Could not resolve all files for configuration ':runtimeClasspath'.\n",
                    "",
                )
            if args[0] == "exec" and "gradle" in args:
                return DockerCommandResult(1, "", "")
            return DockerCommandResult(0, "ok", "")

    validator = DockerTestValidator(
        tmp_path,
        ValidatorSettings(
            python_image=PINNED_PYTHON,
            maven_image=PINNED_MAVEN,
            gradle_image=PINNED_GRADLE,
            gradle_cache_root=cache_root,
        ),
        backend=MissingDependencyBackend(),
    )

    result = validator.run_java_tests(".", build_system="gradle")

    assert result["success"] is False
    assert result["reason"] == "dependency_cache_may_be_stale"
    assert "prepare-gradle" in result["message_to_user"]



def test_snapshot_verified_open_rejects_replaced_file(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("first", encoding="utf-8")
    expected = path.stat()
    path.unlink()
    path.write_text("second", encoding="utf-8")

    with pytest.raises(ValidationError, match="verändert"):
        _open_verified_regular_file(path, expected)


def test_cache_stream_verified_open_rejects_replaced_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"first")
    expected = path.stat()
    path.unlink()
    path.write_bytes(b"second")

    with pytest.raises(ValueError, match="changed during transfer"):
        _open_verified_stream_file(path, expected)



def test_snapshot_enforces_entry_count_limit(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"empty-{index}.txt").write_text("", encoding="utf-8")

    with pytest.raises(ValidationError, match="Eintragslimit"):
        create_project_snapshot(
            tmp_path,
            max_file_bytes=1024,
            max_project_bytes=1024,
            max_snapshot_entries=2,
        )


def test_redaction_discovers_secrets_from_snapshot_not_host_path(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("API_TOKEN=snapshot-secret\n", encoding="utf-8")
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )
    env_file.unlink()
    env_file.symlink_to(tmp_path / "missing-target")

    values = discover_secret_values(snapshot.archive)

    assert "snapshot-secret" in values



def test_snapshot_root_symlink_is_rejected_without_following(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    project = tmp_path / "project"
    project.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValidationError, match="Projektroot"):
        create_project_snapshot(
            project,
            max_file_bytes=1024,
            max_project_bytes=4096,
        )


def test_redaction_scans_config_up_to_snapshot_file_limit(
    tmp_path: Path,
) -> None:
    prefix = "x" * (1_100_000)
    env_file = tmp_path / ".env"
    env_file.write_text(
        prefix + "\nAPI_TOKEN=large-config-secret\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=2 * 1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(
        snapshot.archive,
        max_file_bytes=2 * 1024 * 1024,
    )

    assert "large-config-secret" in values



def test_snapshot_preserves_empty_directories(tmp_path: Path) -> None:
    empty = tmp_path / "tests" / "fixtures" / "empty"
    empty.mkdir(parents=True)

    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024,
        max_project_bytes=4096,
    )

    with tarfile.open(fileobj=io.BytesIO(snapshot.archive), mode="r:") as archive:
        member = archive.getmember("tests/fixtures/empty")

    assert member.isdir()



def test_json_secret_discovery_handles_compact_and_escaped_values(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        '{"name":"demo","api_token":"compact-json-secret",'
        '"api_key":"abcd\\ndefgh","password":"quote\\\"inside"}',
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(snapshot.archive)

    assert "compact-json-secret" in values
    assert "abcd\ndefgh" in values
    assert 'quote"inside' in values


def test_yaml_secret_discovery_uses_yaml_semantics(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "api_token: |2-\n"
        "  line-one\n"
        "  line-two\n"
        "password: !!str >+\n"
        "  folded\n"
        "  secret\n"
        "credentials: &credentials\n"
        "  access_key: anchored-secret\n"
        "copy: *credentials\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(snapshot.archive)

    assert "line-one\nline-two" in values
    assert "folded secret\n" in values
    assert "anchored-secret" in values


def test_toml_secret_discovery_handles_multiline_strings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'api_token = """line-one\nline-two"""\n'
        "password = '''literal-one\nliteral-two'''\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(snapshot.archive)

    assert "line-one\nline-two" in values
    assert "literal-one\nliteral-two" in values


def test_env_and_properties_secret_discovery_use_format_parsers(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        'API_TOKEN="env secret with spaces"\n',
        encoding="utf-8",
    )
    (tmp_path / "application.properties").write_text(
        "service.password=properties\\ value\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(snapshot.archive)

    assert "env secret with spaces" in values
    assert "properties value" in values


def test_properties_secret_discovery_honors_latin1_and_dotted_keys(
    tmp_path: Path,
) -> None:
    properties = (
        "service.api.key=pässwörd\n"
        "service.access.key=zugangsschlüssel\n"
    ).encode("latin-1")
    (tmp_path / "application.properties").write_bytes(properties)
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    values = discover_secret_values(snapshot.archive)

    assert "pässwörd" in values
    assert "zugangsschlüssel" in values


def test_dotenv_parse_error_on_sensitive_line_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        'API_TOKEN="unterminated\n',
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError, match="sensitive .env-Zeile"):
        discover_secret_values(snapshot.archive)


def test_dotenv_sensitive_interpolation_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "BASE=actual-secret\n"
        "API_TOKEN=${BASE}\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError, match="Variableninterpolation"):
        discover_secret_values(snapshot.archive)


def test_malformed_structured_config_with_sensitive_hint_fails_closed(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'api_token = """unterminated\n',
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError, match="sensitiver Schlüssel"):
        discover_secret_values(snapshot.archive)



def test_short_sensitive_value_fails_closed(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"password":"123"}\n', encoding="utf-8")
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError, match="zu kurz"):
        discover_secret_values(snapshot.archive)


def test_yaml_aliases_share_one_structured_work_budget(tmp_path: Path) -> None:
    shared_items = "\n".join(
        f"    item_{index}: {{}}" for index in range(250)
    )
    sensitive_aliases = "\n".join(
        f"token_{index}: *shared" for index in range(500)
    )
    (tmp_path / "config.yaml").write_text(
        "shared: &shared\n"
        f"{shared_items}\n"
        f"{sensitive_aliases}\n",
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError, match="zu groß"):
        discover_secret_values(snapshot.archive)


def test_secret_discovery_fails_closed_when_value_budget_is_exceeded(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"TOKEN_{index}=secret-{index:04d}" for index in range(5)),
        encoding="utf-8",
    )
    snapshot = create_project_snapshot(
        tmp_path,
        max_file_bytes=1024 * 1024,
        max_project_bytes=4 * 1024 * 1024,
    )

    with pytest.raises(SecretDiscoveryLimitError):
        discover_secret_values(snapshot.archive, max_secret_values=2)


def test_output_redactor_suppresses_output_when_discovery_is_incomplete() -> None:
    redactor = OutputRedactor(suppress_output=True)

    result = redactor.redact("API_TOKEN=should-never-be-returned")

    assert "should-never-be-returned" not in result
    assert "unterdrückt" in result


def test_redaction_marker_cannot_reproduce_discovered_secret() -> None:
    redactor = OutputRedactor(["redacted"])

    result = redactor.redact("redacted")

    assert "redacted" not in result
    assert result == "⟦x⟧"


def test_output_redactor_handles_many_exact_values_in_single_pass() -> None:
    secrets = [f"secret-{index:04d}" for index in range(1000)]
    redactor = OutputRedactor(secrets)
    output = "prefix " + " ".join(secrets[::100]) + " suffix"

    result = redactor.redact(output)

    assert not any(secret in result for secret in secrets[::100])
    assert "⟦x⟧" in result


def test_output_redactor_redacts_pem_private_key_block() -> None:
    redactor = OutputRedactor()
    output = (
        "before\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "sensitive-key-material\n"
        "-----END RSA PRIVATE KEY-----\n"
        "after"
    )

    result = redactor.redact(output)

    assert "sensitive-key-material" not in result
    assert "⟦x⟧" in result
    assert "before" in result
    assert "after" in result


def test_exact_secret_cannot_corrupt_pem_boundaries() -> None:
    redactor = OutputRedactor(["PRIVATE KEY"])
    output = (
        "-----BEGIN PRIVATE KEY-----\n"
        "key-material\n"
        "-----END PRIVATE KEY-----\n"
    )

    result = redactor.redact(output)

    assert "key-material" not in result
    assert "⟦x⟧" in result


def test_output_redactor_redacts_unterminated_private_key_to_eof() -> None:
    redactor = OutputRedactor()
    output = (
        "before\n"
        "-----BEGIN PRIVATE KEY-----\n"
        "partial-key-material\n"
    )

    result = redactor.redact(output)

    assert "partial-key-material" not in result
    assert "⟦x⟧" in result
    assert result.startswith("before\n")


def test_output_redactor_handles_many_unmatched_private_key_markers() -> None:
    redactor = OutputRedactor()
    output = (
        "-----BEGIN PRIVATE KEY-----\n" * 5000
        + "no matching end marker"
    )

    result = redactor.redact(output)

    assert result == "⟦x⟧"


def test_output_redactor_redacts_private_key_after_standalone_delimiter() -> None:
    redactor = OutputRedactor()
    output = (
        "-----\n"
        "-----BEGIN PRIVATE KEY-----\n"
        "SECRET\n"
        "-----END PRIVATE KEY-----\n"
    )

    result = redactor.redact(output)

    assert "SECRET" not in result
    assert result.startswith("-----\n")
    assert "⟦x⟧" in result
