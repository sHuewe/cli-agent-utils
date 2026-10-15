from __future__ import annotations

from pathlib import Path

from cli_agent_code_validator_mcp.gradle_cache import (
    gradle_cache_entry,
    sanitize_gradle_home_for_promotion,
)
from cli_agent_code_validator_mcp.maven_cache import cache_entry
from cli_agent_code_validator_mcp.python_cache import python_cache_entry
from cli_agent_code_validator_mcp.cache_cli import (
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

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    entry = prepare_maven(project, cache_root)

    assert entry.is_ready()
    assert (entry.repository / "artifact.jar").is_file()
    assert len(calls) == 3
    assert calls[0][-1] == "dependency:go-offline"
    assert calls[1][-2:] == ["-DskipTests", "package"]
    assert calls[2][-2:] == ["-Dmaven.test.failure.ignore=true", "test"]


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

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    first = prepare_maven(project, cache_root)
    second = prepare_maven(project, cache_root)

    assert first.key == second.key
    assert calls == 6


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
        "cli_agent_code_validator_mcp.cache_cli.default_maven_cache_root",
        lambda: tmp_path / "native-maven",
    )

    root = _resolve_cache_root("maven", explicit=None, target="native")

    assert root == (tmp_path / "native-maven").resolve()


def test_windows_cache_target_from_wsl_uses_windows_user_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.sys.platform",
        "linux",
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.is_wsl",
        lambda: True,
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.default_wsl_windows_cache_root",
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
        "cli_agent_code_validator_mcp.cache_cli.require_wsl",
        lambda: None,
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli._python_interpreter_metadata",
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
        "cli_agent_code_validator_mcp.cache_cli._run_python",
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
        "cli_agent_code_validator_mcp.cache_cli._run_gradle",
        fake_run,
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
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



def test_gradle_promotion_rejects_repository_url_credentials(
    tmp_path: Path,
) -> None:
    import pytest

    gradle_home = tmp_path / "gradle-home"
    metadata = (
        gradle_home
        / "caches"
        / "modules-2"
        / "metadata-2.107"
        / "resource-at-url.bin"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(
        b"prefix https://build-user:super-secret-token@repo.example/artifacts suffix"
    )

    with pytest.raises(Exception, match="eingebetteten Zugangsdaten"):
        sanitize_gradle_home_for_promotion(gradle_home)


def test_gradle_promotion_rejects_repository_url_query_credentials(
    tmp_path: Path,
) -> None:
    import pytest

    gradle_home = tmp_path / "gradle-home"
    metadata = (
        gradle_home
        / "caches"
        / "modules-2"
        / "metadata-2.107"
        / "resource-at-url.bin"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(
        b"prefix https://repo.example/artifacts?token=super-secret-token suffix"
    )

    with pytest.raises(Exception, match="Query-Parametern"):
        sanitize_gradle_home_for_promotion(gradle_home)


def test_gradle_promotion_keeps_repository_metadata_without_url_credentials(
    tmp_path: Path,
) -> None:
    gradle_home = tmp_path / "gradle-home"
    metadata = (
        gradle_home
        / "caches"
        / "modules-2"
        / "metadata-2.107"
        / "resource-at-url.bin"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"prefix https://repo.example/artifacts suffix")

    sanitize_gradle_home_for_promotion(gradle_home)

    assert metadata.is_file()


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

    from cli_agent_code_validator_mcp.python_cache import python_dependency_key

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

    from cli_agent_code_validator_mcp.gradle_cache import gradle_dependency_key

    first = gradle_dependency_key(project)
    plugin.write_text(
        'const val dependency = "com.example:a:2.0"\n',
        encoding="utf-8",
    )
    second = gradle_dependency_key(project)

    assert first == second



def test_python_cache_allows_empty_requirements(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("# no dependencies\n", encoding="utf-8")
    cache_root = tmp_path / "python-cache"

    entry = python_cache_entry(cache_root, project)
    entry.wheels.mkdir(parents=True)
    from cli_agent_code_validator_mcp.python_cache import (
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


def test_prepare_gradle_runtime_resolver_only_resolves_dependencies(
    tmp_path: Path,
) -> None:
    from cli_agent_code_validator_mcp.cache_cli import _write_gradle_runtime_resolver

    script = _write_gradle_runtime_resolver(tmp_path)
    content = script.read_text(encoding="utf-8")

    assert "_cliAgentResolveRuntimeDependencies" in content
    assert "configuration.resolve()" in content
    assert "tasks.withType(org.gradle.api.tasks.testing.Test)" not in content



def test_python_cache_key_is_stable_across_requirement_changes(tmp_path: Path) -> None:
    from cli_agent_code_validator_mcp.python_cache import python_dependency_key

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

    assert first == second



def test_python_plan_requires_requirements_txt(tmp_path: Path) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

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
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

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
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "demo @ https://example.invalid/demo.whl\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="package==version"):
        python_dependency_plan(project)


def test_python_plan_compact_short_option_does_not_echo_credentials(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    secret = "compact-secret-token"
    (project / "requirements.txt").write_text(
        f"-ihttps://user:{secret}@repo.example/simple\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        python_dependency_plan(project)

    message = str(exc_info.value)
    assert secret not in message
    assert "https://user:" not in message


def test_python_plan_include_error_does_not_echo_operand_credentials(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    secret = "include-secret-token"
    (project / "requirements.txt").write_text(
        f"-r https://user:{secret}@repo.example/requirements.txt\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        python_dependency_plan(project)

    message = str(exc_info.value)
    assert secret not in message
    assert "https://user:" not in message


def test_python_plan_rejects_interpolated_requirement_include(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    literal = "${REQ_FILE}"
    (project / literal).write_text("demo-package==1.0\n", encoding="utf-8")
    (project / "requirements.txt").write_text(
        f"-r {literal}\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="Interpolation"):
        python_dependency_plan(project)


def test_python_plan_allows_hash_inside_include_operand(tmp_path: Path) -> None:
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "base.txt#x").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text(
        "-r base.txt#x\n",
        encoding="utf-8",
    )

    plan = python_dependency_plan(project)

    assert plan.has_dependencies


def test_python_plan_does_not_treat_fragment_hash_as_comment(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "base.txt#x").write_text(
        "demo-package==1.0\n",
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text(
        "-r base.txt#x --extra-index-url "
        "https://user:token@example.invalid/simple\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        python_dependency_plan(project)


def test_python_plan_rejects_trailing_tokens_after_include(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "base.txt").write_text("demo-package==1.0\n", encoding="utf-8")
    (project / "requirements.txt").write_text(
        "-r base.txt --extra-index-url https://repo.example/simple\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="Nicht unterstützte Option|package==version"):
        python_dependency_plan(project)


def test_python_plan_rejected_option_does_not_echo_credentials(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    secret = "super-secret-token"
    (project / "requirements.txt").write_text(
        f"--extra-index-url https://user:{secret}@repo.example/simple\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        python_dependency_plan(project)

    message = str(exc_info.value)
    assert "--extra-index-url" in message
    assert secret not in message
    assert "https://user:" not in message


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
        "cli_agent_code_validator_mcp.cache_cli.require_wsl",
        lambda: None,
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli._python_interpreter_metadata",
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
        "cli_agent_code_validator_mcp.cache_cli._run_python",
        fake_run,
    )

    prepare_python(
        project,
        tmp_path / "cache",
        python_command="/usr/bin/python3",
    )

    assert len(calls) == 1
    assert calls[0][-2:] == ["-r", "requirements.txt"]



def test_python_plan_allows_local_packages_outside_project(tmp_path: Path) -> None:
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    sibling = tmp_path / "my_library"
    sibling.mkdir()
    (sibling / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text(
        "../my_library\n", encoding="utf-8",
    )

    assert python_dependency_plan(project).has_dependencies


def test_python_plan_allows_local_file_direct_reference(tmp_path: Path) -> None:
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "demo-package @ file:///mnt/c/dev/demo-package\n",
        encoding="utf-8",
    )

    assert python_dependency_plan(project).has_dependencies


def test_python_plan_rejects_remote_and_editable_sources(tmp_path: Path) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    project.mkdir()
    for requirement in (
        "-e ../my-library",
        "demo @ https://example.invalid/demo.whl",
        "demo @ file://another-host/share/package",
        "git+https://example.invalid/org/repo",
        "https://example.invalid/archive.tar.gz",
        "${PACKAGE_PATH}",
    ):
        (project / "requirements.txt").write_text(
            requirement + "\n", encoding="utf-8",
        )
        with pytest.raises(Exception):
            python_dependency_plan(project)


def test_prepare_python_preserves_local_source_requirement(
    tmp_path: Path, monkeypatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sibling = tmp_path / "my_library"
    sibling.mkdir()
    (sibling / "pyproject.toml").write_text(
        '[project]\nname = "my-library"\nversion = "1.0"\n',
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text(
        "../my_library\n", encoding="utf-8",
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.require_wsl", lambda: None
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli._python_interpreter_metadata",
        lambda _command, *, timeout: {
            "python_version": "3.12.0",
            "python_implementation": "CPython",
            "machine": "x86_64",
        },
    )
    calls = []

    def fake_run(command, *, cwd, timeout):
        calls.append((command, cwd))
        wheels = Path(command[command.index("--wheel-dir") + 1])
        (wheels / "my_library-1.0-py3-none-any.whl").write_bytes(b"wheel")

    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli._run_python", fake_run
    )
    entry = prepare_python(project, tmp_path / "cache", python_command="python3")

    assert entry.is_ready()
    assert (entry.wheels / "my_library-1.0-py3-none-any.whl").is_file()
    assert len(calls) == 1
    assert calls[0][0][-2:] == ["-r", "requirements.txt"]
    assert calls[0][1] == project.resolve()


def test_python_plan_rejects_path_that_only_contains_double_equals(
    tmp_path: Path,
) -> None:
    import pytest
    from cli_agent_code_validator_mcp.python_cache import python_dependency_plan

    project = tmp_path / "project"
    vendor = project / "vendor"
    vendor.mkdir(parents=True)
    (project / "requirements.txt").write_text(
        "./vendor/pkg==1\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="package==version"):
        python_dependency_plan(project)



def test_prepare_maven_accepts_operator_maven_semantics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "project"
    config = project / ".mvn"
    config.mkdir(parents=True)
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    (project / "alt.xml").write_text("<project/>", encoding="utf-8")
    (config / "maven.config").write_text(
        "--settings=../settings.xml\n"
        "-falt.xml\n"
        "-Pcompany\n",
        encoding="utf-8",
    )
    cache_root = tmp_path / "cache"
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        Path(repo_arg.split("=", 1)[1]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    entry = prepare_maven(project, cache_root)

    assert entry.is_ready()
    assert len(calls) == 3

def test_python_interpreter_probe_rejects_windows_python(
    monkeypatch,
) -> None:
    import subprocess
    import pytest
    from cli_agent_code_validator_mcp.cache_cli import _python_interpreter_metadata

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
        "cli_agent_code_validator_mcp.cache_cli.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    with pytest.raises(RuntimeError, match="Linux-Python"):
        _python_interpreter_metadata("python.exe", timeout=30)



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
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
        lambda _command: "mvn",
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int) -> None:
        calls.append(command)
        repo_arg = next(
            value for value in command if value.startswith("-Dmaven.repo.local=")
        )
        Path(repo_arg.split("=", 1)[1]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)

    prepare_maven(project, tmp_path / "cache")

    assert len(calls) == 3



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
        (artifact_dir / "demo-1.0.jar.lastUpdated").write_text(
            "https\\://repo.example/.lastUpdated=1\n",
            encoding="utf-8",
        )
        (artifact_dir / "resolver-status.properties").write_text(
            "maven-metadata-company.xml.lastUpdated=1\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
        lambda _command: "mvn",
    )

    entry = prepare_maven(project, cache_root)

    artifact_dir = entry.repository / "com" / "example" / "demo" / "1.0"
    assert (artifact_dir / "demo-1.0.jar").is_file()
    assert not (artifact_dir / "_remote.repositories").exists()
    assert not (artifact_dir / "demo-1.0.jar.lastUpdated").exists()
    assert not (artifact_dir / "resolver-status.properties").exists()



def test_project_cache_keys_depend_on_project_path_not_dependency_content(
    tmp_path: Path,
) -> None:
    from cli_agent_code_validator_mcp.gradle_cache import gradle_dependency_key
    from cli_agent_code_validator_mcp.maven_cache import maven_dependency_key
    from cli_agent_code_validator_mcp.python_cache import python_dependency_key

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
        "cli_agent_code_validator_mcp.cache_cli.shutil.which",
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

    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli._run", fake_run)

    first = prepare_maven(project, cache_root)
    first_marker = (first.repository / "marker.txt").read_text(encoding="utf-8")
    second = prepare_maven(project, cache_root)
    second_marker = (second.repository / "marker.txt").read_text(encoding="utf-8")

    assert first.key == second.key
    assert first_marker == "3"
    assert second_marker == "6"
    assert len(calls) == 6



def test_windows_target_project_identity_matches_windows_normalization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from cli_agent_code_validator_mcp.cache_identity import windows_project_identity
    from cli_agent_code_validator_mcp.cache_cli import _project_identity_for_target
    import subprocess

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli.sys.platform", "linux")
    monkeypatch.setattr("cli_agent_code_validator_mcp.cache_cli.is_wsl", lambda: True)
    completed = subprocess.CompletedProcess(
        args=["wslpath"],
        returncode=0,
        stdout="C:\\Dev\\Project\n",
        stderr="",
    )
    monkeypatch.setattr(
        "cli_agent_code_validator_mcp.cache_cli.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    identity = _project_identity_for_target(project, "windows")

    assert identity == windows_project_identity("C:\\Dev\\Project")



def test_dependency_cache_cli_program_name() -> None:
    parser = build_parser()
    assert parser.prog == "cli-agent-dependency-cache"
    for command in ("prepare-python", "prepare-maven", "prepare-gradle"):
        assert parser.parse_args([command, "."]).command == command


def test_docker_prepare_cli_accepts_supported_build_systems() -> None:
    parser = build_parser()
    for command in ("prepare-maven", "prepare-gradle", "prepare-python"):
        args = parser.parse_args([command, ".", "--executor", "docker", "--image", "example:latest"])
        assert args.executor == "docker"
        assert args.image == "example:latest"


def test_docker_requirements_snapshot_selective_and_recursive(tmp_path: Path) -> None:
    import io
    import tarfile
    from cli_agent_code_validator_mcp.docker_prepare import _requirements_snapshot
    project = tmp_path / "project"
    (project / "deps").mkdir(parents=True)
    (project / "requirements.txt").write_text("-r deps/base.txt\n", encoding="utf-8")
    (project / "deps" / "base.txt").write_text("-c limits.txt\nfoo==1.0\n", encoding="utf-8")
    (project / "deps" / "limits.txt").write_text("bar==2.0\n", encoding="utf-8")
    (project / "private.py").write_text("SECRET", encoding="utf-8")
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    archive = _requirements_snapshot(project)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert set(tar.getnames()) == {
            "requirements.txt", "deps/base.txt", "deps/limits.txt"
        }


def test_docker_requirements_reject_local_source(tmp_path: Path) -> None:
    import pytest
    from cli_agent_code_validator_mcp.docker_prepare import _requirements_snapshot
    (tmp_path / "requirements.txt").write_text("../shared-lib\n", encoding="utf-8")
    with pytest.raises(Exception, match="Host-Prepare"):
        _requirements_snapshot(tmp_path)


def test_docker_prepare_cleanup_after_create_timeout(tmp_path: Path, monkeypatch) -> None:
    import pytest
    import subprocess
    from cli_agent_code_validator_mcp import docker_prepare
    (tmp_path / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
    calls = []
    class FakeDocker:
        def __init__(self, **kwargs): pass
        def run(self, args, *, timeout, input_bytes=None):
            calls.append(list(args))
            if args[0] == "create":
                raise subprocess.TimeoutExpired("docker create", timeout)
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(docker_prepare, "DockerBackend", FakeDocker)
    with pytest.raises(subprocess.TimeoutExpired):
        docker_prepare.prepare_python_in_docker(
            tmp_path, tmp_path / "cache", image="python:3.12", use_user_config=False
        )
    assert [call[0] for call in calls] == ["create", "rm"]
    assert calls[0][calls[0].index("--name") + 1] == calls[1][-1]


def test_docker_prepare_disabled_pip_config(tmp_path: Path, monkeypatch) -> None:
    import os
    from cli_agent_code_validator_mcp import docker_prepare
    home = tmp_path / "home"
    path = home / ".config" / "pip"
    path.mkdir(parents=True)
    (path / "pip.conf").write_text("[global]\nindex-url = https://secret@example.org\n")
    monkeypatch.setattr(docker_prepare.Path, "home", lambda: home)
    monkeypatch.setenv("PIP_CONFIG_FILE", os.devnull)
    assert docker_prepare._pip_config_snapshot(include_user_config=True) is None


def test_docker_prepare_rejects_invalid_image_reference(tmp_path: Path) -> None:
    import pytest
    from cli_agent_code_validator_mcp.docker_prepare import prepare_python_in_docker
    for image in ("", " ", "-bad", "python:3.12 another"):
        with pytest.raises(ValueError, match="--image"):
            prepare_python_in_docker(tmp_path, tmp_path / "cache", image=image)


def test_docker_wheel_archive_rejects_drive_paths(tmp_path: Path) -> None:
    import io
    import tarfile
    import pytest
    from cli_agent_code_validator_mcp.docker_prepare import _extract_wheel_archive
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        content = b"x"
        item = tarfile.TarInfo("C:/outside.whl")
        item.size = len(content)
        tar.addfile(item, io.BytesIO(content))
    buffer.seek(0)
    with pytest.raises(ValueError, match="ungültige"):
        _extract_wheel_archive(buffer, tmp_path)


def test_docker_prepare_mac_pip_location(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_prepare
    home = tmp_path / "home"
    config = home / "Library" / "Application Support" / "pip"
    config.mkdir(parents=True)
    (config / "pip.conf").write_text("[global]\n")
    monkeypatch.delenv("PIP_CONFIG_FILE", raising=False)
    monkeypatch.setattr(docker_prepare.sys, "platform", "darwin")
    monkeypatch.setattr(docker_prepare.Path, "home", lambda: home)
    assert docker_prepare._pip_user_config() == config / "pip.conf"


def test_docker_prepare_wsl_distribution_requires_wsl(monkeypatch) -> None:
    import pytest
    import sys
    from cli_agent_code_validator_mcp import cache_cli
    monkeypatch.setattr(sys, "argv", [
        "cli-agent-dependency-cache", "prepare-python", ".",
        "--executor", "docker", "--image", "python:3.12",
        "--wsl-distribution", "Ubuntu",
    ])
    with pytest.raises(SystemExit) as err:
        cache_cli.main()
    assert err.value.code == 1


def test_docker_prepare_windows_pip_user_config_fallback(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_prepare
    home = tmp_path / "home"
    modern = tmp_path / "appdata" / "pip" / "pip.ini"
    legacy = home / "pip" / "pip.ini"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[global]\nindex-url = https://legacy.example/simple\n")
    monkeypatch.delenv("PIP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(docker_prepare.sys, "platform", "win32")
    monkeypatch.setattr(docker_prepare.Path, "home", lambda: home)

    assert docker_prepare._pip_user_config() == legacy
    modern.parent.mkdir(parents=True)
    modern.write_text("[global]\nindex-url = https://modern.example/simple\n")
    assert docker_prepare._pip_user_config() == modern


def test_docker_pip_missing_explicit_config_falls_back(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_prepare

    home = tmp_path / "home"
    user_config = home / ".config" / "pip" / "pip.conf"
    user_config.parent.mkdir(parents=True)
    user_config.write_text("[global]\nindex-url = https://example.test/simple\n", encoding="utf-8")
    monkeypatch.setattr(docker_prepare.sys, "platform", "linux")
    monkeypatch.setattr(docker_prepare.Path, "home", lambda: home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("PIP_CONFIG_FILE", str(tmp_path / "missing.conf"))

    assert docker_prepare._pip_user_config() == user_config


def test_docker_pip_macos_xdg_data_home(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_prepare

    home = tmp_path / "home"
    data_home = tmp_path / "xdg-data"
    xdg_config = data_home / "pip" / "pip.conf"
    xdg_config.parent.mkdir(parents=True)
    xdg_config.write_text("[global]\n", encoding="utf-8")
    library_config = home / "Library" / "Application Support" / "pip" / "pip.conf"
    library_config.parent.mkdir(parents=True)
    library_config.write_text("[global]\n", encoding="utf-8")
    monkeypatch.setattr(docker_prepare.sys, "platform", "darwin")
    monkeypatch.setattr(docker_prepare.Path, "home", lambda: home)
    monkeypatch.delenv("PIP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    assert docker_prepare._pip_user_config() == xdg_config
    xdg_config.unlink()
    assert docker_prepare._pip_user_config() != library_config


def test_maven_metadata_readonly_windows_retry(tmp_path: Path, monkeypatch) -> None:
    import stat
    from cli_agent_code_validator_mcp import maven_cache

    repo = tmp_path / "repository"
    repo.mkdir()
    artifact = repo / "artifact.jar"
    artifact.write_bytes(b"jar")
    metadata = repo / "_remote.repositories"
    metadata.write_text("origin")
    monkeypatch.setattr(maven_cache, "_WINDOWS", True)
    original = Path.unlink
    attempts = []

    def fake_unlink(self, *args, **kwargs):
        if self == metadata:
            attempts.append(self.stat().st_mode)
            if len(attempts) == 1:
                raise PermissionError(13, "permission denied", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    metadata.chmod(stat.S_IREAD)
    maven_cache.sanitize_repository_for_offline_use(repo)
    assert len(attempts) == 2
    assert not metadata.exists()
    assert artifact.read_bytes() == b"jar"


def test_maven_metadata_failure_reports_file_and_cause(tmp_path: Path, monkeypatch) -> None:
    import pytest
    from cli_agent_code_validator_mcp import maven_cache

    repo = tmp_path / "repository"
    repo.mkdir()
    metadata = repo / "resolver-status.properties"
    metadata.write_text("metadata")

    def fail_unlink(_path):
        raise PermissionError(13, "locked by process", str(metadata))

    monkeypatch.setattr(maven_cache, "_unlink_maven_metadata", fail_unlink)
    with pytest.raises(Exception, match="resolver-status.properties.*locked by process"):
        maven_cache.sanitize_repository_for_offline_use(repo)
    assert metadata.exists()


def test_maven_failed_prepare_warns_on_cleanup_error(tmp_path: Path, monkeypatch, capsys) -> None:
    import pytest
    from cli_agent_code_validator_mcp import cache_cli
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>")
    cache = tmp_path / "cache"
    monkeypatch.setattr(cache_cli.shutil, "which", lambda command: command)

    def fake_maven(command, *, cwd, timeout):
        raise RuntimeError("Maven failed")

    def fake_cleanup(path):
        raise PermissionError(13, "file locked", str(path))

    monkeypatch.setattr(cache_cli, "_run", fake_maven)
    monkeypatch.setattr(cache_cli, "remove_maven_temporary_cache", fake_cleanup)
    with pytest.raises(RuntimeError, match="Maven failed"):
        cache_cli.prepare_maven(project, cache)
    captured = capsys.readouterr()
    assert "Temporärer Maven-Cache" in captured.err
    assert "file locked" in captured.err


def test_maven_metadata_disappearing_during_cleanup_is_ok(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import maven_cache

    repository = tmp_path / "repository"
    repository.mkdir()
    artifact = repository / "demo.jar"
    artifact.write_bytes(b"artifact")
    metadata = repository / "_remote.repositories"
    metadata.write_text("origin")

    real_unlink = Path.unlink

    def concurrent_unlink(path, *args, **kwargs):
        if path == metadata:
            real_unlink(path)
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", concurrent_unlink)
    maven_cache.sanitize_repository_for_offline_use(repository)
    assert artifact.read_bytes() == b"artifact"
    assert not metadata.exists()


def test_maven_metadata_disappears_before_entry_stat(tmp_path: Path, monkeypatch) -> None:
    import os
    import pytest
    from cli_agent_code_validator_mcp import maven_cache

    repo = tmp_path / "repository"
    repo.mkdir()
    (repo / "demo.jar").write_bytes(b"artifact")
    missing = repo / "resolver-status.properties"
    missing.write_text("metadata")
    real_scandir = maven_cache.os.scandir

    class EntryProxy:
        def __init__(self, entry):
            self._entry = entry
            self.name = entry.name
            self.path = entry.path

        def stat(self, *args, **kwargs):
            if self.name == "resolver-status.properties":
                missing.unlink(missing_ok=True)
                raise FileNotFoundError(2, "File missing", self.path)
            return self._entry.stat(*args, **kwargs)

    class ScanProxy:
        def __init__(self, path):
            self._scan = real_scandir(path)
        def __enter__(self):
            self._scan.__enter__()
            return self
        def __iter__(self):
            return (EntryProxy(entry) for entry in self._scan)
        def __exit__(self, *args):
            return self._scan.__exit__(*args)

    monkeypatch.setattr(maven_cache.os, "scandir", lambda path: ScanProxy(path))
    maven_cache.sanitize_repository_for_offline_use(repo)
    assert (repo / "demo.jar").read_bytes() == b"artifact"


def test_maven_metadata_disappears_during_readonly_retry(tmp_path: Path, monkeypatch) -> None:
    import stat
    import pytest
    from cli_agent_code_validator_mcp import maven_cache

    repo = tmp_path / "repository"
    repo.mkdir()
    metadata = repo / "_remote.repositories"
    metadata.write_text("metadata")
    metadata.chmod(stat.S_IREAD)
    monkeypatch.setattr(maven_cache, "_WINDOWS", True)
    real_unlink = Path.unlink
    calls = 0

    def racing_unlink(path, *args, **kwargs):
        nonlocal calls
        if path == metadata:
            calls += 1
            if calls == 1:
                raise PermissionError(13, "Readonly", str(path))
            real_unlink(path)
            raise FileNotFoundError(2, "Missing", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", racing_unlink)
    maven_cache.sanitize_repository_for_offline_use(repo)
    assert calls == 2
    assert not metadata.exists()


def test_java_docker_cli_options_and_host_guard() -> None:
    import pytest
    parser = build_parser()
    for command in ("prepare-maven", "prepare-gradle"):
        args = parser.parse_args([
            command, ".", "--executor", "docker", "--image", "example:latest", "--wsl"
        ])
        assert args.executor == "docker"
        assert args.image == "example:latest"
        assert args.wsl is True


def test_java_docker_archive_rejects_windows_drive_and_links(tmp_path: Path) -> None:
    import io
    import tarfile
    import pytest
    from cli_agent_code_validator_mcp.docker_java_prepare import _extract_cache_archive
    for malicious in ("C:/outside.jar", "../outside.jar", "/absolute.jar", "nested\\outside.jar"):
        archive_data = io.BytesIO()
        with tarfile.open(fileobj=archive_data, mode="w") as tar:
            info = tarfile.TarInfo(malicious)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        archive_data.seek(0)
        with pytest.raises(ValueError):
            _extract_cache_archive(archive_data, tmp_path)
    link_data = io.BytesIO()
    with tarfile.open(fileobj=link_data, mode="w") as tar:
        info = tarfile.TarInfo("link.jar")
        info.type = tarfile.SYMTYPE
        info.linkname = "real.jar"
        tar.addfile(info)
    link_data.seek(0)
    with pytest.raises(ValueError):
        _extract_cache_archive(link_data, tmp_path)


def test_java_docker_archive_extracts_dependency_tree(tmp_path: Path) -> None:
    import io
    import tarfile
    from cli_agent_code_validator_mcp.docker_java_prepare import _extract_cache_archive
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        info = tarfile.TarInfo("org/demo/artifact.jar")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"jar"))
    stream.seek(0)
    _extract_cache_archive(stream, tmp_path)
    assert (tmp_path / "org" / "demo" / "artifact.jar").read_bytes() == b"jar"


def test_docker_maven_settings_are_selective(tmp_path: Path, monkeypatch) -> None:
    import io
    import tarfile
    from cli_agent_code_validator_mcp import docker_java_prepare
    home = tmp_path / "home"
    (home / ".m2").mkdir(parents=True)
    (home / ".m2" / "settings.xml").write_text("<settings/>")
    (home / ".m2" / "settings-security.xml").write_text("<settingsSecurity/>")
    (home / ".m2" / "repository").mkdir()
    monkeypatch.setattr(docker_java_prepare.Path, "home", lambda: home)
    archive = docker_java_prepare._config_archive("maven", enabled=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert set(tar.getnames()) == {".m2/settings.xml", ".m2/settings-security.xml"}


def test_docker_gradle_user_config_selective(tmp_path: Path) -> None:
    import io
    import tarfile
    from cli_agent_code_validator_mcp.docker_java_prepare import _config_archive

    home = tmp_path / ".gradle"
    home.mkdir()
    (home / "gradle.properties").write_text("repoUser=alice\n")
    (home / "init.gradle").write_text("println 'hello'\n")
    (home / "caches").mkdir()
    (home / "caches" / "secret").write_text("not exported")
    (home / "init.d").mkdir()
    (home / "init.d" / "internal.gradle").write_text("println 'test'\n")

    archive = _config_archive("gradle", enabled=True, gradle_user_home=home)
    assert archive is not None
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert set(tar.getnames()) == {
            "gradle-home/gradle.properties",
            "gradle-home/init.gradle",
            "gradle-home/init.d/internal.gradle",
        }
    assert _config_archive("gradle", enabled=False, gradle_user_home=home) is None


def test_docker_maven_settings_disabled(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_java_prepare
    monkeypatch.setattr(docker_java_prepare.Path, "home", lambda: tmp_path)
    assert docker_java_prepare._config_archive("maven", enabled=False) is None


def test_docker_gradle_exports_only_modules_and_never_user_settings(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_java_prepare as java
    from cli_agent_code_validator_mcp.docker_backend import DockerCommandResult

    project = tmp_path / "project"
    project.mkdir()
    (project / "build.gradle").write_text("plugins { id 'java' }")
    cache_root = tmp_path / "cache"
    user_home = tmp_path / "user-gradle"
    user_home.mkdir()
    (user_home / "gradle.properties").write_text("repoPassword=SECRET")
    exported = []
    executed = []
    payloads = []

    class FakeDocker:
        def __init__(self, **kwargs):
            pass

        def run(self, arguments, *, timeout, input_bytes=None):
            executed.append(arguments)
            payloads.append(input_bytes)
            return DockerCommandResult(0, "", "")

        def stream_tar_directory(self, source, arguments, *, timeout):
            return DockerCommandResult(0, "", "")

    def export(_backend, _name, source, destination, timeout):
        exported.append((source, destination))
        (destination / "artifact.jar").write_bytes(b"jar")

    monkeypatch.setattr(java, "DockerBackend", FakeDocker)
    monkeypatch.setattr(java, "_image_policy", lambda *args: None)
    monkeypatch.setattr(java, "_export_cache", export)
    entry = java.prepare_java_in_docker(
        "gradle", project, cache_root, image="gradle:test",
        gradle_user_home=user_home, verbose=False,
    )
    build_calls = [
        cmd for cmd in executed
        if cmd[:3] == ["exec", "--interactive", "--workdir"]
    ]
    assert len(build_calls) == 1
    build_cmd = build_calls[0]
    assert "--env" in build_cmd
    assert "JAVA_TOOL_OPTIONS=-Duser.home=/tmp/home" not in build_cmd
    assert "--interactive" in build_cmd
    assert build_cmd[build_cmd.index("sh") + 1:build_cmd.index("sh") + 3] == ["-s", "--"]
    assert "-c" not in build_cmd
    assert build_cmd[-1] == "_cliAgentResolveRuntimeDependencies"
    build_payload = payloads[executed.index(build_cmd)]
    assert build_payload is not None
    assert b'JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+${JAVA_TOOL_OPTIONS} }' in build_payload
    assert b'-Duser.home=/tmp/home"' in build_payload
    assert b'exec "$@"' in build_payload
    assert len(exported) == 1
    assert exported[0][0] == "/tmp/prepared/gradle-home/caches/modules-2"
    # Export first lands in a temporary cache directory. Only after validation
    # is it promoted to the final, stable entry path.
    exported_path = exported[0][1]
    relative = exported_path.relative_to(cache_root)
    assert relative.parts[0].startswith(".prep-")
    assert relative.parts[1:] == ("gradle-home", "caches", "modules-2")
    assert not exported_path.exists()
    assert (entry.gradle_home / "caches" / "modules-2" / "artifact.jar").read_bytes() == b"jar"
    assert not (entry.gradle_home / "gradle.properties").exists()
    assert not (entry.gradle_home / "init.gradle").exists()
    assert "SECRET" not in str(list(entry.directory.rglob("*")))

def test_docker_prepare_output_mode_default_and_quiet() -> None:
    parser = build_parser()
    for command in ("prepare-maven", "prepare-gradle", "prepare-python"):
        normal = parser.parse_args([command, ".", "--executor", "docker", "--image", "local:test"])
        quiet = parser.parse_args([command, ".", "--executor", "docker", "--image", "local:test", "--quiet"])
        verbose = parser.parse_args([command, ".", "--executor", "docker", "--image", "local:test", "--verbose"])
        assert normal.verbose is True
        assert quiet.verbose is False
        assert verbose.verbose is True


def test_docker_prepare_build_output_streams_to_terminal(monkeypatch) -> None:
    import subprocess
    from cli_agent_code_validator_mcp.docker_prepare import _run_build_with_output
    from cli_agent_code_validator_mcp.docker_backend import DockerCommandResult

    class Backend:
        def command(self, *args):
            return ["docker", *args]

        def run(self, args, *, timeout, input_bytes=None):
            return DockerCommandResult(0, "", "")

    invocations = []

    def fake_run(cmd, *, input, timeout, check):
        invocations.append((cmd, input, timeout, check))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = ["exec", "-i", "container", "sh", "-s", "--", "mvn", "package"]
    _run_build_with_output(Backend(), runner, 123, data=b'exec "$@"\n')
    assert invocations == [(["docker", *runner], b'exec "$@"\n', 123, False)]


def test_docker_prepare_live_output_failure_and_quiet(monkeypatch) -> None:
    import subprocess
    import pytest
    from cli_agent_code_validator_mcp.docker_prepare import _run_build_with_output
    from cli_agent_code_validator_mcp.docker_backend import DockerCommandResult

    class Backend:
        def command(self, *args):
            return ["docker", *args]

        def run(self, args, *, timeout, input_bytes=None):
            return DockerCommandResult(126, "", "")

    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, *, input, timeout, check: subprocess.CompletedProcess(cmd, 126),
    )
    with pytest.raises(RuntimeError, match="Exit 126"):
        _run_build_with_output(Backend(), ["exec", "container", "mvn"], 120)
    with pytest.raises(RuntimeError, match="Exit 126"):
        _run_build_with_output(Backend(), ["exec", "container", "mvn"], 120, verbose=False)


def test_java_docker_quiet_forwarded_from_cli(tmp_path: Path, monkeypatch) -> None:
    import sys
    from types import SimpleNamespace
    from cli_agent_code_validator_mcp import cache_cli, docker_java_prepare

    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>")
    (project / "build.gradle").write_text("plugins { id 'java' }")
    calls = []

    def fake_prepare(kind, path, root, **kwargs):
        calls.append((kind, kwargs["verbose"]))
        return SimpleNamespace(key="test", repository=root / "repository",
                               gradle_home=root / "gradle-home")

    monkeypatch.setattr(docker_java_prepare, "prepare_java_in_docker", fake_prepare)
    for cmd, expected in (
        ("prepare-maven", False), ("prepare-gradle", False),
        ("prepare-maven", True), ("prepare-gradle", True),
    ):
        argv = ["cli-agent-dependency-cache", cmd, str(project),
                "--executor", "docker", "--image", "test:local",
                "--cache-root", str(tmp_path / "cache")]
        if not expected:
            argv.append("--quiet")
        monkeypatch.setattr(sys, "argv", argv)
        cache_cli.main()
    assert calls == [
        ("maven", False), ("gradle", False),
        ("maven", True), ("gradle", True),
    ]


def test_windows_cache_promotion_retries_transient_denial(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_prepare
    original = Path.rename
    calls = []

    src = tmp_path / "pending"
    dst = tmp_path / "ready"
    src.mkdir()
    (src / "artifact.jar").write_bytes(b"jar")

    def flaky_rename(self, target):
        calls.append((self, target))
        if self == src and len(calls) == 1:
            error = PermissionError(13, "Access denied", str(self))
            error.winerror = 5
            raise error
        return original(self, target)

    monkeypatch.setattr(docker_prepare, "_WINDOWS", True)
    monkeypatch.setattr(docker_prepare.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(Path, "rename", flaky_rename)
    docker_prepare._promote_cache(src, dst)
    assert len(calls) == 2
    assert (dst / "artifact.jar").read_bytes() == b"jar"


def test_windows_cache_promotion_does_not_retry_unrelated_errors(tmp_path: Path, monkeypatch) -> None:
    import pytest
    from cli_agent_code_validator_mcp import docker_prepare
    src = tmp_path / "pending"
    dst = tmp_path / "ready"
    src.mkdir()

    def failed_rename(self, target):
        error = PermissionError(13, "Access denied", str(self))
        error.winerror = 123
        raise error

    monkeypatch.setattr(docker_prepare.os, "name", "nt")
    monkeypatch.setattr(Path, "rename", failed_rename)
    with pytest.raises(PermissionError):
        docker_prepare._promote_cache(src, dst)
    assert src.exists()

def test_maven_failed_test_warmup_preserves_previous_cache(tmp_path: Path, monkeypatch) -> None:
    import pytest
    from cli_agent_code_validator_mcp import cache_cli
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>")
    calls = []

    def runner(command, *, cwd, timeout):
        calls.append(command)
        if command[-1] == "test":
            raise RuntimeError("Maven-Vorbereitung endete mit Code 1.")

    monkeypatch.setattr(cache_cli, "_run", runner)
    with pytest.raises(RuntimeError, match="Code 1"):
        cache_cli.prepare_maven(project, tmp_path / "cache")
    assert [c[-1] for c in calls] == ["dependency:go-offline", "package", "test"]


def test_maven_test_warmup_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import cache_cli
    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>")
    calls = []

    def runner(command, *, cwd, timeout):
        calls.append(command[-1])
        Path(next(x.split("=", 1)[1] for x in command if x.startswith("-Dmaven.repo.local="))).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cache_cli, "_run", runner)
    cache_cli.prepare_maven(project, tmp_path / "cache", test_warmup=False)
    assert calls == ["dependency:go-offline", "package"]
    args = build_parser().parse_args(["prepare-maven", ".", "--skip-test-warmup"])
    assert args.skip_test_warmup is True



def test_docker_maven_warmup_failure_rejects_cache(tmp_path: Path, monkeypatch) -> None:
    from cli_agent_code_validator_mcp import docker_java_prepare as java
    from cli_agent_code_validator_mcp.docker_backend import DockerCommandResult

    project = tmp_path / "project"
    project.mkdir()
    (project / "pom.xml").write_text("<project/>")
    cache_root = tmp_path / "cache"
    build_commands = []

    class FakeDocker:
        def __init__(self, **kwargs):
            pass

        def run(self, args, *, timeout, input_bytes=None):
            return DockerCommandResult(0, "", "")

        def stream_tar_directory(self, source, args, *, timeout):
            return DockerCommandResult(0, "", "")

    def run_build(backend, args, timeout, *, data=None, verbose=True):
        build_commands.append(args)
        if args[-1] == "test":
            raise RuntimeError("test failure")

    def export(backend, container, source, dest, timeout):
        (dest / "provider.jar").write_bytes(b"provider")

    monkeypatch.setattr(java, "DockerBackend", FakeDocker)
    monkeypatch.setattr(java, "_image_policy", lambda *args: None)
    monkeypatch.setattr(java, "_run_build_with_output", run_build)
    monkeypatch.setattr(java, "_export_cache", export)
    import pytest
    with pytest.raises(RuntimeError, match="test failure"):
        java.prepare_java_in_docker(
            "maven", project, cache_root, image="maven:test",
            use_user_config=False, verbose=False,
        )
    assert not list(cache_root.glob("maven-*"))
    assert [cmd[-1] for cmd in build_commands] == [
        "dependency:go-offline", "package", "test"
    ]
    assert "-Dmaven.test.failure.ignore=true" in build_commands[-1]
