from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cli_agent_compose_mcp.compose import ComposeError, ComposeProject, find_compose_file


def test_find_compose_file_prefers_compose_yaml(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    expected = tmp_path / "compose.yaml"
    expected.write_text("services: {}", encoding="utf-8")
    assert find_compose_file(tmp_path) == expected.resolve()


def test_find_compose_file_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ComposeError, match="Keine Compose-Datei"):
        find_compose_file(tmp_path)


def test_logs_validates_service_and_uses_tail_200(tmp_path: Path) -> None:
    (tmp_path / "compose.yaml").write_text("services: {}", encoding="utf-8")
    project = ComposeProject.from_directory(tmp_path)
    responses = [Mock(returncode=0, stdout="web\n", stderr=""), Mock(returncode=0, stdout="last line\n", stderr="")]
    with patch("cli_agent_compose_mcp.compose.subprocess.run", side_effect=responses) as run:
        assert project.logs("web") == "last line"
    assert run.call_args_list[1].args[0][-5:] == ["logs", "--tail", "200", "--no-color", "web"]
