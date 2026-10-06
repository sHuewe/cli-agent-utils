from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

from .maven_cache import (
    MavenCacheEntry,
    default_maven_cache_root,
    maven_dependency_key,
    write_ready_metadata,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli-agent-test-cache",
        description=(
            "Prepare dependency caches for the offline cli-agent test validator. "
            "This command runs as the current user and may use the user's normal "
            "Maven/JFrog configuration."
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
            [*common, "-DskipTests", "test"],
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


def main() -> None:
    args = build_parser().parse_args()
    if args.command != "prepare-maven":
        raise RuntimeError(f"Unbekannter Befehl: {args.command}")
    try:
        entry = prepare_maven(
            args.project,
            args.cache_root,
            maven_command=args.maven_command,
            timeout=args.timeout,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Maven dependency key: {entry.key}")
    print(f"Cache repository: {entry.repository}")
    print("Cache ready for offline validator use.")


if __name__ == "__main__":
    main()
