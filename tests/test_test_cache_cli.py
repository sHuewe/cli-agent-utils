from __future__ import annotations

from pathlib import Path

from cli_agent_mcp.maven_cache import cache_entry
from cli_agent_mcp.test_cache_cli import prepare_maven


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
    assert calls[1][-2:] == ["-DskipTests", "test"]


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
