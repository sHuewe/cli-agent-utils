from __future__ import annotations

from pathlib import Path

from cli_agent_mcp.gradle_cache import gradle_cache_entry
from cli_agent_mcp.maven_cache import cache_entry, default_maven_cache_root
from cli_agent_mcp.python_cache import python_cache_entry
from cli_agent_mcp.test_cache_cli import (
    _resolve_cache_root,
    build_parser,
    prepare_gradle,
    prepare_maven,
    prepare_python,
)


def test_prepare_maven_builds_isolated_repository_and_marks_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "cache"
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        repository = Path(repo_arg.split("=", 1)[1])
        repository.mkdir(parents=True, exist_ok=True)
        (repository / "artifact.jar").write_bytes(b"jar")

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    entry = prepare_maven(project, cache_root)

    assert entry.is_ready()
    assert (entry.repository / "artifact.jar").is_file()
    assert len(calls) == 2
    assert calls[0][-1] == "dependency:go-offline"
    assert calls[1][-2:] == ["-DskipTests", "package"]


def test_prepare_maven_reuses_ready_cache_without_running_maven(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "cache"

    calls = 0

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        nonlocal calls
        calls += 1
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        repository = Path(repo_arg.split("=", 1)[1])
        repository.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    first = prepare_maven(project, cache_root)
    second = prepare_maven(project, cache_root)

    assert first.key == second.key
    assert calls == 2


def test_cache_key_matches_validator_lookup(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "cache"

    entry = cache_entry(cache_root, project)

    assert entry.directory == cache_root.resolve() / entry.key


def test_prepare_parser_uses_native_target_by_default() -> None:
    args = build_parser().parse_args(["prepare-maven", "."])

    assert args.cache_root is None
    assert args.target == "native"


def test_native_cache_target_uses_current_environment_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.default_maven_cache_root",
        lambda: tmp_path / "native-maven",
    )

    root = _resolve_cache_root("maven", explicit=None, target="native")

    assert root == (tmp_path / "native-maven").resolve()


def test_windows_cache_target_from_wsl_uses_windows_user_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.sys.platform",
        "linux",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.is_wsl",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.default_wsl_windows_cache_root",
        lambda name: tmp_path / "windows-cache" / name,
    )

    root = _resolve_cache_root("gradle", explicit=None, target="windows")

    assert root == (tmp_path / "windows-cache" / "gradle").resolve()


def test_explicit_cache_root_rejects_windows_target(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="--cache-root"):
        _resolve_cache_root(
            "python",
            explicit=tmp_path / "custom",
            target="windows",
        )


def test_prepare_python_requires_wsl_and_builds_wheel_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    cache_root = tmp_path / "python-cache"
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.require_wsl",
        lambda: None,
    )

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        wheel_dir = Path(command[command.index("--wheel-dir") + 1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        (wheel_dir / "demo_package-1.0-py3-none-any.whl").write_bytes(b"wheel")

    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._run_python",
        fake_run,
    )

    entry = prepare_python(
        project,
        cache_root,
        python_command="/usr/bin/python3",
    )

    assert entry.is_ready()
    assert (
        entry.wheels / "demo_package-1.0-py3-none-any.whl"
    ).is_file()
    assert len(calls) == 1
    assert calls[0][:4] == [
        "/usr/bin/python3",
        "-m",
        "pip",
        "wheel",
    ]
    assert calls[0][-2:] == ["-r", "requirements.txt"]


def test_python_cache_entry_matches_preparation_key(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    cache_root = tmp_path / "python-cache"

    entry = python_cache_entry(cache_root, project)

    assert entry.directory == cache_root.resolve() / entry.key
    assert entry.key.startswith("python-")


def test_prepare_gradle_builds_isolated_gradle_home_and_removes_user_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "build.gradle").write_text("plugins {}", encoding="utf-8")
    cache_root = tmp_path / "gradle-cache"
    user_home = tmp_path / "user-gradle"
    user_home.mkdir()
    (user_home / "gradle.properties").write_text(
        "repoToken=secret\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        gradle_home = Path(command[command.index("--gradle-user-home") + 1])
        cache_dir = gradle_home / "caches"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "artifact.bin").write_bytes(b"cache")

    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._run_gradle",
        fake_run,
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "gradle",
    )

    entry = prepare_gradle(
        project,
        cache_root,
        source_gradle_user_home=user_home,
    )

    assert entry.is_ready()
    assert (entry.gradle_home / "caches" / "artifact.bin").is_file()
    assert not (entry.gradle_home / "gradle.properties").exists()
    assert len(calls) == 1
    assert "--refresh-dependencies" in calls[0]
    assert calls[0][-2:] == ["assemble", "testClasses"]


def test_gradle_cache_entry_matches_preparation_key(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
    cache_root = tmp_path / "gradle-cache"

    entry = gradle_cache_entry(cache_root, project)

    assert entry.directory == cache_root.resolve() / entry.key
    assert entry.key.startswith("gradle-")
