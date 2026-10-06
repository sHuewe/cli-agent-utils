from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_agent_mcp.docker_backend import DockerBackend, DockerCommandResult
from cli_agent_mcp.gradle_cache import (
    gradle_cache_entry,
    write_gradle_ready_metadata,
)
from cli_agent_mcp.maven_cache import cache_entry, maven_dependency_key, write_ready_metadata
from cli_agent_mcp.python_cache import (
    python_cache_entry,
    python_dependency_plan,
    write_python_ready_metadata,
)
from cli_agent_mcp.test_validator import DockerTestValidator
from cli_agent_mcp.test_validator_redaction import OutputRedactor
from cli_agent_mcp.test_validator_server import _workspace_from_core_environment
from cli_agent_mcp.test_validator_snapshot import create_project_snapshot
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


def test_output_redactor_removes_known_and_generic_secrets() -> None:
    redactor = OutputRedactor(["super-secret-value"])

    text = redactor.redact(
        "value=super-secret-value\nAuthorization: Bearer abcdef\npassword=hunter2"
    )

    assert "super-secret-value" not in text
    assert "abcdef" not in text
    assert "hunter2" not in text
    assert "<redacted>" in text


def test_python_tests_use_fixed_no_shell_command_and_redact_output(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "API_TOKEN=super-secret-value\n",
        encoding="utf-8",
    )
    (tmp_path / "test_demo.py").write_text(
        "def test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    backend = FakeBackend(exec_output="token=super-secret-value\n1 passed")
    validator = DockerTestValidator(tmp_path, settings(), backend=backend)

    result = validator.run_python_tests(".", "test_demo.py::test_ok")

    assert result["success"] is True
    assert result["container_removed"] is True
    assert "super-secret-value" not in result["output"]
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
    assert exec_call[-6:] == [
        "mvn",
        "-o",
        "-B",
        "-Dmaven.repo.local=/tmp/m2",
        "-Dtest=com.example.ExampleTest#works",
        "test",
    ]
    cache_setup = next(
        args
        for args, _ in backend.calls
        if args[0] == "exec" and "/opt/cli-agent-test-cache/maven" in " ".join(args)
    )
    assert "sh" in cache_setup


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
        "com.example.ExampleTest.works",
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
    assert any(
        "/opt/cli-agent-test-cache/gradle" in " ".join(args)
        for args, _ in backend.calls
        if args[0] == "exec"
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


def test_maven_dependency_key_changes_with_relevant_pom(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project>A</project>", encoding="utf-8")
    first = maven_dependency_key(tmp_path)

    (tmp_path / "pom.xml").write_text("<project>B</project>", encoding="utf-8")
    second = maven_dependency_key(tmp_path)

    assert first.startswith("maven-")
    assert first != second


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
    assert "prepare-python" in result["message"]


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
        and "/tmp/python-wheels" in args
    )
    assert "--target" in install
    assert "/tmp/python-deps" in install


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
