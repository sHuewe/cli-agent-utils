"""Trusted, operator-invoked Maven/Gradle preparation in Docker.

This module is never exposed as MCP. Docker build scripts run with network
access and may consume the explicitly selected user's repository credentials.
Only validated dependency artifacts are promoted to the offline validator.
"""
from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess  # nosec B404
import tarfile
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath, PureWindowsPath

from .docker_backend import DockerBackend
from .docker_prepare import _check, _docker_run, _run_build_with_output, _files_tar, _image_policy, _promote_cache, _regular_file_bytes
from .gradle_cache import (
    GradleCacheEntry, default_source_gradle_user_home, gradle_cache_entry,
    sanitize_gradle_home_for_promotion, seed_gradle_user_configuration,
    write_gradle_ready_metadata,
)
from .maven_cache import MAVEN_TEST_WARMUP_ARGS, MavenCacheEntry, cache_entry, sanitize_repository_for_offline_use, write_ready_metadata

_MAX_EXPORTED_BYTES = 3 * 1024**3
_MAX_EXPORTED_FILES = 100_000
_TRANSFER_TIMEOUT = 600


def _config_archive(kind: str, *, enabled: bool, gradle_user_home: Path | None = None) -> bytes | None:
    if not enabled:
        return None
    files: dict[str, bytes] = {}
    if kind == "maven":
        home = Path.home() / ".m2"
        for name in ("settings.xml", "settings-security.xml"):
            src = home / name
            if src.is_symlink():
                raise ValueError("Maven-Konfiguration darf kein Symlink sein.")
            if src.is_file():
                files[f".m2/{name}"] = _regular_file_bytes(src, limit=1024 * 1024)
    else:
        home = gradle_user_home or default_source_gradle_user_home()
        with tempfile.TemporaryDirectory() as temp:
            copied = seed_gradle_user_configuration(home, Path(temp))
            for path in copied:
                files["gradle-home/" + path.relative_to(temp).as_posix()] = _regular_file_bytes(
                    path, limit=1024 * 1024
                )
    return _files_tar(files) if files else None


def _extract_cache_archive(stream, destination: Path) -> None:
    """Strict cache-only TAR extraction; reject traversal, links, devices and duplicates."""
    total = count = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name in ("", "."):
                if member.isdir():
                    continue
                raise ValueError("Ungültiger Cache-Archiv-Eintrag.")
            posix = PurePosixPath(name)
            windows = PureWindowsPath(name)
            if (posix.is_absolute() or windows.drive or windows.is_absolute()
                    or ".." in posix.parts or "\\" in name or ":" in name
                    or any(ord(char) < 32 for char in name)):
                raise ValueError("Unsicherer Pfad im Docker-Cache.")
            path = destination.joinpath(*posix.parts)
            if path.exists() or path.is_symlink():
                raise ValueError("Doppelter Cache-Archiv-Eintrag.")
            count += 1
            total += member.size
            if count > _MAX_EXPORTED_FILES or total > _MAX_EXPORTED_BYTES:
                raise ValueError("Docker-Cache überschreitet Transferlimit.")
            if member.isdir():
                path.mkdir(parents=True)
            elif member.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Unlesbares Cache-Archiv.")
                with path.open("xb") as target:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Unvollständiger Cache-Export.")
                        target.write(chunk)
                        remaining -= len(chunk)
            else:
                raise ValueError("Nur reguläre Dateien und Ordner im Cache erlaubt.")


def _export_cache(backend: DockerBackend, container: str, source: str, dest: Path, timeout: int) -> None:
    command = backend.command("exec", container, "tar", "-C", source, "-cf", "-", ".")
    with tempfile.TemporaryFile() as tmp:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)  # nosec B603
        assert process.stdout is not None
        def transfer():
            length = 0
            with process.stdout:
                while True:
                    buf = process.stdout.read(1024 * 1024)
                    if not buf:
                        break
                    length += len(buf)
                    if length > _MAX_EXPORTED_BYTES + 32 * 1024 * 1024:
                        raise ValueError("Docker-Cache-Archiv zu groß.")
                    tmp.write(buf)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(transfer)
            try:
                future.result(timeout=timeout)
                status = process.wait(timeout=30)
                if status:
                    raise RuntimeError("Docker-Cache-Export fehlgeschlagen.")
            except BaseException:
                if process.poll() is None:
                    process.kill()
                process.wait()
                raise
        tmp.seek(0)
        _extract_cache_archive(tmp, dest)


def prepare_java_in_docker(
    kind: str, project: Path, cache_root: Path, *, image: str,
    timeout: int = 1800, project_identity: str | None = None,
    use_user_config: bool = True, gradle_user_home: Path | None = None,
    wsl: bool = False, wsl_distribution: str | None = None,
    verbose: bool = True, test_warmup: bool = True,
) -> MavenCacheEntry | GradleCacheEntry:
    """Explicit trusted CLI operation; never callable through MCP."""
    if kind not in ("maven", "gradle"):
        raise ValueError("Unbekanntes Build-System.")
    if not image or image != image.strip() or image.startswith("-") or any(ch.isspace() for ch in image):
        raise ValueError("--image muss eine gültige Docker-Image-Referenz sein.")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")
    project = project.expanduser().resolve()
    root = cache_root.expanduser().resolve()
    entry = (cache_entry(root, project, project_identity=project_identity)
             if kind == "maven" else gradle_cache_entry(root, project, project_identity=project_identity))
    root.mkdir(parents=True, exist_ok=True)
    if entry.directory.is_symlink():
        raise ValueError("Cache-Eintrag darf kein Symlink sein.")
    config = _config_archive(kind, enabled=use_user_config, gradle_user_home=gradle_user_home)
    _config_members = set()
    if config is not None:
        with tarfile.open(fileobj=io.BytesIO(config)) as package:
            _config_members = {Path(m.name).name for m in package.getmembers()}
    backend = DockerBackend(wsl=wsl, wsl_distribution=wsl_distribution)
    name = "cli-agent-prepare-" + uuid.uuid4().hex
    temp = Path(tempfile.mkdtemp(dir=root, prefix=".prep-"))
    try:
        if verbose:
            print(f"[prepare-{kind}] Docker-Container erstellen ...", flush=True)
        _docker_run(backend, [
            "create", "--name", name, "--pull", "never",
            "--user", "65532:65532", "--read-only",
            "--tmpfs", "/work:rw,nosuid,nodev,size=2g,uid=65532,gid=65532,mode=0700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=4g,uid=65532,gid=65532,mode=0700",
            "--network", "bridge", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "256", "--memory", "4g", "--cpus", "2",
            "--env", "HOME=/tmp/home", "--entrypoint", "sh",
            image, "-c",
            "mkdir -p /tmp/home/.m2 /tmp/home/.gradle /tmp/prepared /work/project; while :; do sleep 3600; done",
        ], 60)
        _image_policy(backend, name)
        _docker_run(backend, ["start", name], 60)
        # The trusted project is copied, never bind-mounted. The streaming
        # backend rejects symlinks, reparse points and other special entries.
        if verbose:
            print(f"[prepare-{kind}] Projekt übertragen ...", flush=True)
        result = backend.stream_tar_directory(project, [
            "exec", "-i", name, "tar", "-C", "/work/project", "-xf", "-"
        ], timeout=_TRANSFER_TIMEOUT)
        _check(result, "project transfer")
        if config is not None:
            _docker_run(backend, ["exec", "-i", name, "tar", "-C", "/tmp/home" if kind == "maven" else "/tmp/prepared", "-xf", "-"],
                        _TRANSFER_TIMEOUT, data=config)
        if kind == "maven":
            commands = (
                ["mvn", "-B", "-Dmaven.repo.local=/tmp/prepared/repository",
                 *(["-s", "/tmp/home/.m2/settings.xml"] if config is not None
                   and "settings.xml" in _config_members else []),
                 "dependency:go-offline"],
                ["mvn", "-B", "-Dmaven.repo.local=/tmp/prepared/repository",
                 *(["-s", "/tmp/home/.m2/settings.xml"] if config is not None
                   and "settings.xml" in _config_members else []),
                 "-DskipTests", "package"],
            )
            # Maven's default ~/.m2 settings live below /tmp/home/.m2
            _docker_run(backend, ["exec", name, "mkdir", "-p", "/tmp/prepared/repository"], 30)
        else:
            # Config is staged in /tmp/home/gradle to avoid exporting it.
            # A custom resolution task ensures resolvable runtime configurations.
            init = b'gradle.projectsEvaluated { gradle.rootProject.tasks.register("_cliAgentResolveRuntimeDependencies") { doLast { gradle.rootProject.allprojects.each { p -> p.configurations.findAll { c -> c.canBeResolved && (c.name == "runtimeClasspath" || c.name == "testRuntimeClasspath" || c.name.endsWith("RuntimeClasspath")) }.each { c -> c.resolve() } } } } }\n'
            _docker_run(
                backend, ["exec", "-i", name, "tar", "-C", "/tmp/prepared", "-xf", "-"],
                30, data=_files_tar({"runtime.init.gradle": init}),
            )
            commands = ([
                "gradle", "--no-daemon", "--refresh-dependencies",
                "--gradle-user-home", "/tmp/prepared/gradle-home",
                "--init-script", "/tmp/prepared/runtime.init.gradle",
                "assemble", "testClasses", "_cliAgentResolveRuntimeDependencies",
            ],)
        for cmd in commands:
            if verbose:
                print(f"[prepare-{kind}] Build: {cmd[-1]} ...", flush=True)
            # Preserve JAVA_TOOL_OPTIONS supplied by the selected image (CA,
            # proxy, agents, etc.). Docker exec --env would replace it; the
            # shell instead appends our home setting without re-evaluating
            # or interpolating the image-provided value as shell code.
            build_args = [
                "exec", "--interactive", "--workdir", "/work/project",
                "--env", "HOME=/tmp/home", name, "sh", "-s", "--", *cmd,
            ]
            _run_build_with_output(
                backend, build_args, timeout,
                data=(
                    b'JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+${JAVA_TOOL_OPTIONS} }'
                    b'-Duser.home=/tmp/home"; export JAVA_TOOL_OPTIONS; exec "$@"\n'
                ),
                verbose=verbose,
            )
        if kind == "maven" and test_warmup:
            # Warm dynamically resolved Surefire/JUnit providers without
            # making test failures fatal to cache promotion.
            if verbose:
                print("[prepare-maven] Test-Warm-up (Testfehler erlaubt) ...", flush=True)
            warmup_args = [
                "exec", "--interactive", "--workdir", "/work/project",
                "--env", "HOME=/tmp/home", name, "sh", "-s", "--",
                *commands[1][:-2], *MAVEN_TEST_WARMUP_ARGS,
            ]
            # Maven's test-failure-ignore option handles assertion failures.
            # Missing providers or plugin failures must prevent cache promotion.
            _run_build_with_output(
                backend, warmup_args, timeout,
                data=(
                    b'JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+${JAVA_TOOL_OPTIONS} }'
                    b'-Duser.home=/tmp/home"; export JAVA_TOOL_OPTIONS; exec "$@"\n'
                ),
                verbose=verbose,
            )
        if verbose:
            print(f"[prepare-{kind}] Dependency-Cache exportieren ...", flush=True)
        if kind == "maven":
            repository = temp / "repository"
            repository.mkdir()
            _export_cache(backend, name, "/tmp/prepared/repository", repository, timeout)
            sanitize_repository_for_offline_use(repository)
            write_ready_metadata(temp, entry.key)
        else:
            # User-provided gradle.properties and init scripts reside in the
            # container's Gradle home. Never copy that home to the host:
            # a crash before sanitization could leave plaintext credentials.
            # Export only downloaded modules, then apply the existing cache
            # validation and repository-metadata checks before promotion.
            modules = temp / "gradle-home" / "caches" / "modules-2"
            modules.mkdir(parents=True)
            _docker_run(
                backend,
                ["exec", name, "mkdir", "-p",
                 "/tmp/prepared/gradle-home/caches/modules-2"],
                30,
            )
            _export_cache(
                backend, name, "/tmp/prepared/gradle-home/caches/modules-2",
                modules, timeout,
            )
            sanitize_gradle_home_for_promotion(temp / "gradle-home")
            write_gradle_ready_metadata(temp, entry.key)
        _promote_cache(temp, entry.directory)
        return entry
    finally:
        try:
            backend.run(["rm", "-f", "-v", name], timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
