from __future__ import annotations

from pathlib import Path

from cli_agent_mcp.gradle_cache import gradle_cache_entry
from cli_agent_mcp.maven_cache import cache_entry
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


def test_prepare_maven_rebuilds_ready_cache(
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
    assert calls == 4


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


def test_explicit_cache_root_is_allowed_with_windows_target(tmp_path: Path) -> None:
    root = _resolve_cache_root(
        "python",
        explicit=tmp_path / "custom",
        target="windows",
    )

    assert root == (tmp_path / "custom").resolve()


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
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._python_interpreter_metadata",
        lambda _command, *, timeout: {
            "python_version": "3.12.0",
            "python_implementation": "CPython",
            "machine": "x86_64",
        },
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
        modules = gradle_home / "caches" / "modules-2" / "files-2.1"
        modules.mkdir(parents=True, exist_ok=True)
        (modules / "artifact.bin").write_bytes(b"cache")
        compiled = gradle_home / "caches" / "jars-9" / "init"
        compiled.mkdir(parents=True, exist_ok=True)
        (compiled / "Init.class").write_bytes(b"repoToken=secret")

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
    assert (
        entry.gradle_home
        / "caches"
        / "modules-2"
        / "files-2.1"
        / "artifact.bin"
    ).is_file()
    assert not (entry.gradle_home / "gradle.properties").exists()
    assert not (entry.gradle_home / "caches" / "jars-9").exists()
    assert len(calls) == 1
    assert "--refresh-dependencies" in calls[0]
    assert "--init-script" in calls[0]
    assert calls[0][-3:] == [
        "assemble",
        "testClasses",
        "_cliAgentResolveRuntimeDependencies",
    ]


def test_gradle_cache_entry_matches_preparation_key(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
    cache_root = tmp_path / "gradle-cache"

    entry = gradle_cache_entry(cache_root, project)

    assert entry.directory == cache_root.resolve() / entry.key
    assert entry.key.startswith("gradle-")



def test_python_nested_requirements_are_resolved_relative_to_including_file(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    nested = project / "requirements"
    nested.mkdir(parents=True)
    (project / "requirements.txt").write_text(
        "-r requirements/base.txt\n",
        encoding="utf-8",
    )
    (nested / "base.txt").write_text("-r common.txt\n", encoding="utf-8")
    (nested / "common.txt").write_text("demo-package==1.0\n", encoding="utf-8")

    from cli_agent_mcp.python_cache import python_dependency_key

    key = python_dependency_key(project)

    assert key.startswith("python-")


def test_gradle_cache_key_is_stable_across_included_build_logic_changes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "build.gradle.kts").write_text("", encoding="utf-8")
    (project / "settings.gradle.kts").write_text(
        'includeBuild("build-logic")\n',
        encoding="utf-8",
    )
    source = project / "build-logic" / "src" / "main" / "kotlin"
    source.mkdir(parents=True)
    plugin = source / "ConventionPlugin.kt"
    plugin.write_text(
        'const val dependency = "com.example:a:1.0"\n',
        encoding="utf-8",
    )

    from cli_agent_mcp.gradle_cache import gradle_dependency_key

    first = gradle_dependency_key(project)
    plugin.write_text(
        'const val dependency = "com.example:a:2.0"\n',
        encoding="utf-8",
    )
    second = gradle_dependency_key(project)

    assert first == second



def test_prepare_maven_rejects_semantic_user_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    settings = tmp_path / "settings.xml"
    settings.write_text(
        """
<settings>
  <profiles>
    <profile>
      <id>company</id>
      <properties><revision>1.2.3</revision></properties>
    </profile>
  </profiles>
</settings>
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="Build-Semantik"):
        prepare_maven(project, tmp_path / "cache")



def test_python_cache_allows_empty_requirements(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("# no dependencies\n", encoding="utf-8")
    cache_root = tmp_path / "python-cache"

    entry = python_cache_entry(cache_root, project)
    entry.wheels.mkdir(parents=True)
    from cli_agent_mcp.python_cache import (
        python_dependency_plan,
        write_python_ready_metadata,
    )

    write_python_ready_metadata(
        entry.directory,
        entry.key,
        python_dependency_plan(project),
    )

    assert entry.is_ready()
    assert entry.install_wheel_names() == ()


def test_prepare_gradle_runtime_resolver_disables_test_tasks(
    tmp_path: Path,
) -> None:
    from cli_agent_mcp.test_cache_cli import _write_gradle_runtime_resolver

    script = _write_gradle_runtime_resolver(tmp_path)
    content = script.read_text(encoding="utf-8")

    assert "tasks.withType(org.gradle.api.tasks.testing.Test)" in content
    assert "enabled = false" in content



def test_python_cache_key_is_stable_across_requirement_changes(tmp_path: Path) -> None:
    from cli_agent_mcp.python_cache import python_dependency_key

    project = tmp_path / "project"
    requirements = project / "requirements"
    requirements.mkdir(parents=True)
    (project / "requirements.txt").write_text(
        "-rrequirements/base.txt\n",
        encoding="utf-8",
    )
    nested = requirements / "base.txt"
    nested.write_text("demo-package==1.0\n", encoding="utf-8")

    first = python_dependency_key(project)
    nested.write_text("demo-package==2.0\n", encoding="utf-8")
    second = python_dependency_key(project)

    assert first != second



def test_python_plan_requires_requirements_txt(tmp_path: Path) -> None:
    import pytest
    from cli_agent_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n',
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="requirements.txt"):
        python_dependency_plan(project)


def test_python_plan_rejects_unpinned_requirement(tmp_path: Path) -> None:
    import pytest
    from cli_agent_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "requests>=2\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="package==version"):
        python_dependency_plan(project)


def test_python_plan_rejects_direct_url_requirement(tmp_path: Path) -> None:
    import pytest
    from cli_agent_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "demo @ https://example.invalid/demo.whl\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="package==version"):
        python_dependency_plan(project)


def test_prepare_python_resolves_requirements_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    nested = project / "requirements"
    nested.mkdir(parents=True)
    (project / "requirements.txt").write_text(
        "-r requirements/test.txt\nrequests==2.32.0\n",
        encoding="utf-8",
    )
    (nested / "test.txt").write_text("pytest==9.0.0\n", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.require_wsl",
        lambda: None,
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._python_interpreter_metadata",
        lambda _command, *, timeout: {
            "python_version": "3.12.0",
            "python_implementation": "CPython",
            "machine": "x86_64",
        },
    )

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        wheel_dir = Path(command[command.index("--wheel-dir") + 1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        (wheel_dir / "requests-2.32.0-py3-none-any.whl").write_bytes(b"wheel")
        (wheel_dir / "pytest-9.0.0-py3-none-any.whl").write_bytes(b"wheel")

    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._run_python",
        fake_run,
    )

    prepare_python(
        project,
        tmp_path / "cache",
        python_command="/usr/bin/python3",
    )

    assert len(calls) == 1
    assert calls[0][-2:] == ["-r", "requirements.txt"]



def test_python_plan_rejects_path_that_only_contains_double_equals(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    vendor = project / "vendor"
    vendor.mkdir(parents=True)
    (project / "requirements.txt").write_text(
        "./vendor/pkg==1\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="package==version"):
        python_dependency_plan(project)


def test_prepare_maven_rejects_compact_settings_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "-s../settings.xml\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )

    with pytest.raises(RuntimeError, match="Projekt-spezifische Maven-Settings"):
        prepare_maven(project, tmp_path / "cache")


def test_prepare_maven_rejects_long_settings_equals_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "--settings=../settings.xml\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )

    with pytest.raises(RuntimeError, match="Projekt-spezifische Maven-Settings"):
        prepare_maven(project, tmp_path / "cache")



def test_prepare_maven_rejects_compact_global_settings_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "-gs../global-settings.xml\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )

    with pytest.raises(RuntimeError, match="global-settings"):
        prepare_maven(project, tmp_path / "cache")


def test_prepare_maven_rejects_long_global_settings_equals_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "--global-settings=../global-settings.xml\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )

    with pytest.raises(RuntimeError, match="global-settings"):
        prepare_maven(project, tmp_path / "cache")



def test_python_interpreter_probe_rejects_windows_python(
    monkeypatch,
) -> None:
    import subprocess
    import pytest
    from cli_agent_mcp.test_cache_cli import _python_interpreter_metadata

    completed = subprocess.CompletedProcess(
        args=["python.exe"],
        returncode=0,
        stdout=(
            '{"sys_platform":"win32","python_version":"3.12.0",'
            '"python_implementation":"CPython","machine":"AMD64"}\n'
        ),
        stderr="",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    with pytest.raises(RuntimeError, match="Linux-Python"):
        _python_interpreter_metadata("python.exe", timeout=30)



def test_prepare_maven_rejects_alternate_pom_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (project / "alt.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "-falt.xml\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )

    with pytest.raises(RuntimeError, match="Alternative Maven-Projektdateien"):
        prepare_maven(project, tmp_path / "cache")


def test_prepare_maven_allows_fail_at_end_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text("-fae\n", encoding="utf-8")
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        Path(repo_arg.split("=", 1)[1]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)

    prepare_maven(project, tmp_path / "cache")

    assert len(calls) == 2



def test_prepare_maven_removes_remote_repository_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    cache_root = tmp_path / "cache"

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        repository = Path(repo_arg.split("=", 1)[1])
        artifact_dir = repository / "com" / "example" / "demo" / "1.0"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "demo-1.0.jar").write_bytes(b"jar")
        (artifact_dir / "_remote.repositories").write_text(
            "demo-1.0.jar>company-mirror=\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    entry = prepare_maven(project, cache_root)

    artifact_dir = entry.repository / "com" / "example" / "demo" / "1.0"
    assert (artifact_dir / "demo-1.0.jar").is_file()
    assert not (artifact_dir / "_remote.repositories").exists()



def test_prepare_maven_ignores_commented_settings_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "# --settings was removed\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        Path(repo_arg.split("=", 1)[1]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)

    prepare_maven(project, tmp_path / "cache")

    assert len(calls) == 2



def test_project_cache_keys_depend_on_project_path_not_dependency_content(
    tmp_path: Path,
) -> None:
    from cli_agent_mcp.gradle_cache import gradle_dependency_key
    from cli_agent_mcp.maven_cache import maven_dependency_key
    from cli_agent_mcp.python_cache import python_dependency_key

    first_project = tmp_path / "first"
    second_project = tmp_path / "second"
    first_project.mkdir()
    second_project.mkdir()

    for project in (first_project, second_project):
        (project / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        (project / "build.gradle").write_text("", encoding="utf-8")
        (project / "requirements.txt").write_text(
            "demo-package==1.0\n",
            encoding="utf-8",
        )

    assert maven_dependency_key(first_project) != maven_dependency_key(second_project)
    assert gradle_dependency_key(first_project) != gradle_dependency_key(second_project)
    assert python_dependency_key(first_project) != python_dependency_key(second_project)


def test_prepare_maven_rebuilds_existing_project_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli._default_maven_settings_path",
        lambda: tmp_path / "missing-settings.xml",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repository_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        repository = Path(repository_arg.split("=", 1)[1])
        repository.mkdir(parents=True, exist_ok=True)
        (repository / "marker.txt").write_text(
            str(len(calls)),
            encoding="utf-8",
        )

    monkeypatch.setattr("cli_agent_mcp.test_cache_cli._run", fake_run)

    first = prepare_maven(project, cache_root)
    first_marker = (first.repository / "marker.txt").read_text(encoding="utf-8")
    second = prepare_maven(project, cache_root)
    second_marker = (second.repository / "marker.txt").read_text(encoding="utf-8")

    assert first.key == second.key
    assert first_marker == "2"
    assert second_marker == "4"
    assert len(calls) == 4



def test_windows_target_project_identity_matches_windows_normalization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from cli_agent_mcp.cache_identity import windows_project_identity
    from cli_agent_mcp.test_cache_cli import _project_identity_for_target
    import subprocess

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("cli_agent_mcp.test_cache_cli.sys.platform", "linux")
    monkeypatch.setattr("cli_agent_mcp.test_cache_cli.is_wsl", lambda: True)
    completed = subprocess.CompletedProcess(
        args=["wslpath"],
        returncode=0,
        stdout="C:\\Dev\\Project\n",
        stderr="",
    )
    monkeypatch.setattr(
        "cli_agent_mcp.test_cache_cli.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    identity = _project_identity_for_target(project, "windows")

    assert identity == windows_project_identity("C:\\Dev\\Project")
