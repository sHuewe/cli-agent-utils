from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .gradle_cache import (
    GradleCacheEntry,
    default_gradle_cache_root,
    default_source_gradle_user_home,
    gradle_dependency_key,
    remove_seeded_gradle_user_configuration,
    sanitize_gradle_home_for_promotion,
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
    default_python_cache_root,
    default_wsl_windows_cache_root,
    is_wsl,
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
        default=None,
        help=(
            "Explicit shared Maven cache root. Do not combine with --target windows."
        ),
    )
    prepare.add_argument(
        "--target",
        choices=("native", "windows"),
        default="native",
        help=(
            "Cache location target. 'native' uses this environment's "
            "~/.cli-agent cache; 'windows' targets the Windows user's cache "
            "when preparation runs in WSL."
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
        default=None,
        help=(
            "Explicit shared Gradle cache root. Do not combine with --target windows."
        ),
    )
    prepare_gradle.add_argument(
        "--target",
        choices=("native", "windows"),
        default="native",
        help=(
            "Cache location target. 'native' uses this environment's "
            "~/.cli-agent cache; 'windows' targets the Windows user's cache "
            "when preparation runs in WSL."
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
            "Explicit Python cache root. Do not combine with --target windows."
        ),
    )
    prepare_python.add_argument(
        "--target",
        choices=("native", "windows"),
        default="native",
        help=(
            "Cache location target. 'native' uses the WSL user's "
            "~/.cli-agent cache for a WSL-hosted MCP; 'windows' writes to "
            "the Windows user's corresponding cache for a Windows-hosted MCP."
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


def _resolve_cache_root(
    cache_name: str,
    *,
    explicit: Path | None,
    target: str,
) -> Path:
    if explicit is not None:
        if target != "native":
            raise ValueError(
                "--cache-root kann nicht mit --target windows kombiniert werden."
            )
        return explicit.expanduser().resolve()
    if target == "native":
        defaults = {
            "maven": default_maven_cache_root,
            "gradle": default_gradle_cache_root,
            "python": default_python_cache_root,
        }
        return defaults[cache_name]().expanduser().resolve()
    if target == "windows":
        if sys.platform == "win32":
            defaults = {
                "maven": default_maven_cache_root,
                "gradle": default_gradle_cache_root,
                "python": default_python_cache_root,
            }
            return defaults[cache_name]().expanduser().resolve()
        if is_wsl():
            return default_wsl_windows_cache_root(cache_name).resolve()
        raise ValueError(
            "--target windows ist nur unter Windows oder WSL verfügbar."
        )
    raise ValueError(f"Unbekanntes Cache-Ziel: {target}")


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


def _default_maven_settings_path() -> Path:
    return Path.home() / ".m2" / "settings.xml"


def _reject_semantic_maven_settings(project: Path) -> None:
    maven_config = project / ".mvn" / "maven.config"
    if maven_config.is_file():
        try:
            config_text = maven_config.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise RuntimeError(
                ".mvn/maven.config konnte nicht gelesen werden."
            ) from exc
        tokens = config_text.split()
        has_settings_option = any(
            token == "-s"
            or token.startswith("-s")
            or token == "--settings"
            or token.startswith("--settings=")
            or token == "-gs"
            or token.startswith("-gs")
            or token == "--global-settings"
            or token.startswith("--global-settings=")
            for token in tokens
        )
        if has_settings_option:
            raise RuntimeError(
                "Projekt-spezifische Maven-Settings via "
                "-s/--settings oder -gs/--global-settings werden vom "
                "Offline-Validator nicht unterstützt."
            )

    settings = _default_maven_settings_path()
    if not settings.is_file():
        return
    try:
        root = ET.parse(settings).getroot()
    except (OSError, ET.ParseError) as exc:
        raise RuntimeError(
            "Maven settings.xml konnte nicht sicher ausgewertet werden."
        ) from exc

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    for element in root.iter():
        name = local_name(element.tag)
        if name in {"profiles", "activeProfiles"} and list(element):
            raise RuntimeError(
                "Maven settings.xml enthält Build-Semantik über "
                f"{name}. Der Offline-Validator unterstützt settings.xml nur "
                "für Repository-/Mirror-/Credential-Konfiguration. "
                "Verschiebe aktive Profile/Properties in die Projekt-POM "
                "oder verwende eine settings.xml ohne Build-Semantik."
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

    _reject_semantic_maven_settings(project)
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


def _write_gradle_runtime_resolver(directory: Path) -> Path:
    script = directory / "cli-agent-resolve-runtime.gradle"
    script.write_text(
        """allprojects {
    tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {
        enabled = false
    }
}
gradle.projectsEvaluated {
    def root = gradle.rootProject
    root.tasks.register("_cliAgentResolveRuntimeDependencies") {
        doLast {
            root.allprojects.each { project ->
                project.configurations.findAll { configuration ->
                    configuration.canBeResolved && (
                        configuration.name == "runtimeClasspath" ||
                        configuration.name == "testRuntimeClasspath" ||
                        configuration.name.endsWith("RuntimeClasspath")
                    )
                }.each { configuration ->
                    configuration.resolve()
                }
            }
        }
    }
}
""",
        encoding="utf-8",
    )
    return script


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
    runtime_resolver = _write_gradle_runtime_resolver(temporary)
    try:
        _run_gradle(
            [
                *command_prefix,
                "--no-daemon",
                "--refresh-dependencies",
                "--gradle-user-home",
                str(gradle_home),
                "--init-script",
                str(runtime_resolver),
                "assemble",
                "testClasses",
                "_cliAgentResolveRuntimeDependencies",
            ],
            cwd=project,
            timeout=timeout,
        )
        runtime_resolver.unlink(missing_ok=True)
        remove_seeded_gradle_user_configuration(gradle_home, copied)
        copied = ()
        sanitize_gradle_home_for_promotion(gradle_home)
        write_gradle_ready_metadata(temporary, key)
        if entry.directory.exists():
            shutil.rmtree(entry.directory)
        temporary.replace(entry.directory)
        return entry
    except BaseException:
        runtime_resolver.unlink(missing_ok=True)
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


def _python_interpreter_metadata(
    python_command: str,
    *,
    timeout: int,
) -> dict[str, str]:
    probe = (
        "import json, platform, sys; "
        "print(json.dumps({"
        "'sys_platform': sys.platform, "
        "'python_version': platform.python_version(), "
        "'python_implementation': platform.python_implementation(), "
        "'machine': platform.machine()"
        "}))"
    )
    try:
        completed = subprocess.run(  # nosec B603
            [python_command, "-c", probe],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=min(timeout, 30),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Der für --python-command ausgewählte Interpreter konnte nicht "
            "geprüft werden."
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            "Der für --python-command ausgewählte Interpreter konnte nicht "
            "geprüft werden."
        )
    try:
        value = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Der für --python-command ausgewählte Interpreter lieferte "
            "ungültige Plattforminformationen."
        ) from exc
    if not isinstance(value, dict) or not all(
        isinstance(value.get(name), str)
        for name in (
            "sys_platform",
            "python_version",
            "python_implementation",
            "machine",
        )
    ):
        raise RuntimeError(
            "Der für --python-command ausgewählte Interpreter lieferte "
            "unvollständige Plattforminformationen."
        )
    if not value["sys_platform"].startswith("linux"):
        raise RuntimeError(
            "Python-Dependencies müssen mit einem Linux-Python unter WSL "
            "vorbereitet werden. --python-command darf keinen Windows-"
            "Interpreter auswählen."
        )
    return {
        "python_version": value["python_version"],
        "python_implementation": value["python_implementation"],
        "machine": value["machine"],
    }


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

    interpreter_metadata = _python_interpreter_metadata(
        python_command,
        timeout=timeout,
    )

    root = (
        cache_root.expanduser().resolve()
        if cache_root is not None
        else default_python_cache_root().resolve()
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
        _run_python(
            [*common, "-r", "requirements.txt"],
            cwd=project,
            timeout=timeout,
        )
        write_python_ready_metadata(
            temporary,
            key,
            plan,
            interpreter_metadata=interpreter_metadata,
        )
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
            cache_root = _resolve_cache_root(
                "maven",
                explicit=args.cache_root,
                target=args.target,
            )
            entry = prepare_maven(
                args.project,
                cache_root,
                maven_command=args.maven_command,
                timeout=args.timeout,
                force=args.force,
            )
            print(f"Maven dependency key: {entry.key}")
            print(f"Cache repository: {entry.repository}")
            print("Cache ready for offline validator use.")
            return

        if args.command == "prepare-gradle":
            cache_root = _resolve_cache_root(
                "gradle",
                explicit=args.cache_root,
                target=args.target,
            )
            entry = prepare_gradle(
                args.project,
                cache_root,
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
            cache_root = _resolve_cache_root(
                "python",
                explicit=args.cache_root,
                target=args.target,
            )
            entry = prepare_python(
                args.project,
                cache_root,
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
