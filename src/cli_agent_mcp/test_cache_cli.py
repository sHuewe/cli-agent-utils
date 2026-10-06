from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

from .gradle_cache import (
    GradleCacheEntry,
    default_gradle_cache_root,
    default_source_gradle_user_home,
    gradle_dependency_key,
    remove_seeded_gradle_user_configuration,
    seed_gradle_user_configuration,
    write_gradle_ready_metadata,
)
from .maven_cache import (
    MavenCacheEntry,
    default_maven_cache_root,
    maven_dependency_key,
    write_ready_metadata,
)
from .python_cache import (
    PythonCacheEntry,
    default_wsl_python_cache_root,
    python_dependency_key,
    python_dependency_plan,
    require_wsl,
    write_python_ready_metadata,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli-agent-test-cache",
        description=(
            "Prepare dependency caches for the offline cli-agent test validator. "
            "This command runs as the current user and may use normal Maven, "
            "Gradle or pip/PyPI/JFrog configuration. Python preparation requires WSL."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser(
        "prepare-maven",
        help="Prepare a project-specific Maven repository for offline tests.",
    )
    prepare.add_argument("project", type=Path)
    prepare.add_argument(
        "--cache-root",
        type=Path,
        default=default_maven_cache_root(),
        help=(
            "Shared Maven cache root. Configure the same absolute path as "
            "--maven-cache-root for cli-agent-test-validator-mcp."
        ),
    )
    prepare.add_argument(
        "--maven-command",
        default="mvn",
        help="Maven executable used for preparation (default: mvn).",
    )
    prepare.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout per Maven preparation command in seconds.",
    )
    prepare.add_argument(
        "--force",
        action="store_true",
        help="Rebuild an already prepared cache entry.",
    )

    prepare_gradle = subparsers.add_parser(
        "prepare-gradle",
        help="Prepare a project-specific Gradle user home for offline tests.",
    )
    prepare_gradle.add_argument("project", type=Path)
    prepare_gradle.add_argument(
        "--cache-root",
        type=Path,
        default=default_gradle_cache_root(),
        help=(
            "Shared Gradle cache root. Configure the same absolute path as "
            "--gradle-cache-root for cli-agent-test-validator-mcp."
        ),
    )
    prepare_gradle.add_argument(
        "--gradle-command",
        default=None,
        help=(
            "Gradle executable used for preparation. By default a project "
            "Gradle wrapper is preferred, then gradle from PATH."
        ),
    )
    prepare_gradle.add_argument(
        "--source-gradle-user-home",
        type=Path,
        default=default_source_gradle_user_home(),
        help=(
            "Existing user Gradle home used only as a source for "
            "gradle.properties/init scripts during preparation."
        ),
    )
    prepare_gradle.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout for Gradle dependency preparation in seconds.",
    )
    prepare_gradle.add_argument(
        "--force",
        action="store_true",
        help="Rebuild an already prepared cache entry.",
    )

    prepare_python = subparsers.add_parser(
        "prepare-python",
        help=(
            "Prepare Linux-compatible Python wheels for offline tests. "
            "This command must be run inside WSL."
        ),
    )
    prepare_python.add_argument("project", type=Path)
    prepare_python.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help=(
            "Python cache root. By default the Windows user's "
            "~/.cli-agent/dependency-cache/python directory is resolved "
            "from WSL so the Windows MCP can read the same cache."
        ),
    )
    prepare_python.add_argument(
        "--python-command",
        default=sys.executable,
        help=(
            "Python interpreter used for pip wheel preparation "
            "(default: current WSL Python)."
        ),
    )
    prepare_python.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout per pip wheel command in seconds.",
    )
    prepare_python.add_argument(
        "--force",
        action="store_true",
        help="Rebuild an already prepared cache entry.",
    )
    return parser


def _run(command: list[str], *, cwd: Path, timeout: int) -> None:
    completed = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Maven-Vorbereitung endete mit Code {completed.returncode}."
        )


def prepare_maven(
    project: Path,
    cache_root: Path,
    *,
    maven_command: str = "mvn",
    timeout: int = 1800,
    force: bool = False,
) -> MavenCacheEntry:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Projektverzeichnis existiert nicht: {project}")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")

    key = maven_dependency_key(project)
    root = cache_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    entry = MavenCacheEntry(root=root, key=key)
    if entry.directory.is_symlink():
        raise RuntimeError(
            "Der Maven-Cache-Eintrag darf kein Symlink sein."
        )
    if entry.directory.exists() and not force:
        if entry.is_ready():
            return entry
        raise RuntimeError(
            "Der Maven-Cache-Eintrag existiert, ist aber nicht vollständig. "
            "Verwende --force zum Neuaufbau."
        )

    executable = shutil.which(maven_command) or maven_command
    temporary = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=root))
    repository = temporary / "repository"
    repository.mkdir(parents=True)
    try:
        common = [
            executable,
            "-B",
            f"-Dmaven.repo.local={repository}",
        ]
        _run(
            [*common, "dependency:go-offline"],
            cwd=project,
            timeout=timeout,
        )
        _run(
            [*common, "-DskipTests", "package"],
            cwd=project,
            timeout=timeout,
        )
        write_ready_metadata(temporary, key)

        if entry.directory.exists():
            shutil.rmtree(entry.directory)
        temporary.replace(entry.directory)
        return entry
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def prepare_gradle(
    project: Path,
    cache_root: Path,
    *,
    gradle_command: str | None = None,
    source_gradle_user_home: Path | None = None,
    timeout: int = 1800,
    force: bool = False,
) -> GradleCacheEntry:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Projektverzeichnis existiert nicht: {project}")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")

    key = gradle_dependency_key(project)
    root = cache_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    entry = GradleCacheEntry(root=root, key=key)
    if entry.directory.is_symlink():
        raise RuntimeError("Der Gradle-Cache-Eintrag darf kein Symlink sein.")
    if entry.directory.exists() and not force:
        if entry.is_ready():
            return entry
        raise RuntimeError(
            "Der Gradle-Cache-Eintrag existiert, ist aber nicht vollständig. "
            "Verwende --force zum Neuaufbau."
        )

    command_prefix: list[str]
    if gradle_command:
        command_prefix = [shutil.which(gradle_command) or gradle_command]
    elif sys.platform == "win32" and (project / "gradlew.bat").is_file():
        command_prefix = ["cmd.exe", "/d", "/c", str(project / "gradlew.bat")]
    elif (project / "gradlew").is_file():
        command_prefix = [str(project / "gradlew")]
    else:
        command_prefix = [shutil.which("gradle") or "gradle"]

    temporary = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=root))
    gradle_home = temporary / "gradle-home"
    gradle_home.mkdir(parents=True)
    source_home = (
        source_gradle_user_home.expanduser().resolve()
        if source_gradle_user_home is not None
        else default_source_gradle_user_home()
    )
    copied = seed_gradle_user_configuration(source_home, gradle_home)
    try:
        _run_gradle(
            [
                *command_prefix,
                "--no-daemon",
                "--refresh-dependencies",
                "--gradle-user-home",
                str(gradle_home),
                "testClasses",
            ],
            cwd=project,
            timeout=timeout,
        )
        remove_seeded_gradle_user_configuration(gradle_home, copied)
        copied = ()
        write_gradle_ready_metadata(temporary, key)
        if entry.directory.exists():
            shutil.rmtree(entry.directory)
        temporary.replace(entry.directory)
        return entry
    except BaseException:
        if copied:
            try:
                remove_seeded_gradle_user_configuration(gradle_home, copied)
            except Exception:
                pass
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _run_gradle(command: list[str], *, cwd: Path, timeout: int) -> None:
    completed = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Gradle-Vorbereitung endete mit Code {completed.returncode}."
        )


def prepare_python(
    project: Path,
    cache_root: Path | None,
    *,
    python_command: str = sys.executable,
    timeout: int = 1800,
    force: bool = False,
) -> PythonCacheEntry:
    require_wsl()
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Projektverzeichnis existiert nicht: {project}")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")

    root = (
        cache_root.expanduser().resolve()
        if cache_root is not None
        else default_wsl_python_cache_root().resolve()
    )
    root.mkdir(parents=True, exist_ok=True)
    key = python_dependency_key(project)
    plan = python_dependency_plan(project)
    entry = PythonCacheEntry(root=root, key=key)
    if entry.directory.is_symlink():
        raise RuntimeError("Der Python-Cache-Eintrag darf kein Symlink sein.")
    if entry.directory.exists() and not force:
        if entry.is_ready():
            return entry
        raise RuntimeError(
            "Der Python-Cache-Eintrag existiert, ist aber nicht vollständig. "
            "Verwende --force zum Neuaufbau."
        )

    temporary = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=root))
    wheels = temporary / "wheels"
    wheels.mkdir(parents=True)
    try:
        common = [
            python_command,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--wheel-dir",
            str(wheels),
        ]
        for requirement in plan.requirement_files:
            _run_python(
                [*common, "-r", requirement],
                cwd=project,
                timeout=timeout,
            )
        if plan.dependency_specs:
            _run_python(
                [*common, *plan.dependency_specs],
                cwd=project,
                timeout=timeout,
            )
        write_python_ready_metadata(temporary, key, plan)
        if entry.directory.exists():
            shutil.rmtree(entry.directory)
        temporary.replace(entry.directory)
        return entry
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _run_python(command: list[str], *, cwd: Path, timeout: int) -> None:
    completed = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Python-Dependency-Vorbereitung endete mit Code "
            f"{completed.returncode}."
        )


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare-maven":
            entry = prepare_maven(
                args.project,
                args.cache_root,
                maven_command=args.maven_command,
                timeout=args.timeout,
                force=args.force,
            )
            print(f"Maven dependency key: {entry.key}")
            print(f"Cache repository: {entry.repository}")
            print("Cache ready for offline validator use.")
            return

        if args.command == "prepare-gradle":
            entry = prepare_gradle(
                args.project,
                args.cache_root,
                gradle_command=args.gradle_command,
                source_gradle_user_home=args.source_gradle_user_home,
                timeout=args.timeout,
                force=args.force,
            )
            print(f"Gradle dependency key: {entry.key}")
            print(f"Cache Gradle user home: {entry.gradle_home}")
            print("Cache ready for offline validator use.")
            return

        if args.command == "prepare-python":
            print(
                "Python dependency preparation: WSL is required. "
                "Building Linux-compatible wheels with the current user's "
                "pip/PyPI configuration."
            )
            entry = prepare_python(
                args.project,
                args.cache_root,
                python_command=args.python_command,
                timeout=args.timeout,
                force=args.force,
            )
            print(f"Python dependency key: {entry.key}")
            print(f"Wheel cache: {entry.wheels}")
            print("Prepared under WSL: yes")
            print(
                "Cache ready for offline Linux Docker validator use."
            )
            return

        raise RuntimeError(f"Unbekannter Befehl: {args.command}")
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
