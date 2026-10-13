"""Trusted, explicitly user-invoked dependency preparation in a temporary Docker container.

This is intentionally NOT the offline MCP validator sandbox. Network is always
Docker bridge; a small whitelist of user config files is sent into tmpfs.
Only sanitized dependency artifacts are promoted to the host cache.
"""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess  # nosec B404
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from .code_validator_snapshot import create_project_snapshot
from .docker_backend import DockerBackend
from .gradle_cache import (
    GradleCacheEntry,
    gradle_cache_entry,
    sanitize_gradle_home_for_promotion,
    write_gradle_ready_metadata,
)
from .maven_cache import (
    MavenCacheEntry,
    cache_entry,
    sanitize_repository_for_offline_use,
    write_ready_metadata,
)
from .python_cache import (
    PythonCacheEntry,
    python_cache_entry,
    python_dependency_plan,
    write_python_ready_metadata,
)

_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_RETURN_BYTES = 4 * 1024 * 1024 * 1024
_MAX_RETURN_FILES = 100_000
_TRANSFER_TIMEOUT = 300


def _config_file(files: dict[str, Path], name: str, path: Path) -> None:
    """Include only a named regular file, never symlinks, directories or junctions."""
    if path.is_symlink():
        raise ValueError("Benutzerkonfiguration darf kein Symlink sein.")
    if not path.exists():
        return
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_CONFIG_BYTES:
        raise ValueError("Benutzerkonfiguration muss eine reguläre, kleine Datei sein.")
    files[name] = path


def _pip_user_config() -> Path | None:
    """Choose the highest-priority explicit/user config, not entire pip config dirs."""
    override = os.environ.get("PIP_CONFIG_FILE")
    if override and override != os.devnull:
        return Path(override).expanduser()
    home = Path.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "pip" / "pip.ini" if appdata else home / "pip" / "pip.ini"
    candidates = [
        home / ".config" / "pip" / "pip.conf",
        home / ".pip" / "pip.conf",
    ]
    return next((p for p in candidates if p.is_file() or p.is_symlink()), None)


def _user_configuration(
    kind: str,
    *,
    gradle_user_home: Path | None,
    include_user_config: bool,
) -> dict[str, Path]:
    if not include_user_config:
        return {}
    files: dict[str, Path] = {}
    if kind == "maven":
        home = Path.home() / ".m2"
        _config_file(files, "maven/settings.xml", home / "settings.xml")
        _config_file(files, "maven/settings-security.xml", home / "settings-security.xml")
    elif kind == "gradle":
        home = (gradle_user_home or Path(os.environ.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))).expanduser()
        for name in ("gradle.properties", "init.gradle", "init.gradle.kts"):
            _config_file(files, "gradle/" + name, home / name)
        init = home / "init.d"
        if init.is_symlink():
            raise ValueError("Gradle init.d darf kein Symlink sein.")
        if init.exists():
            if not init.is_dir():
                raise ValueError("Gradle init.d muss ein Verzeichnis sein.")
            for child in sorted(init.iterdir()):
                _config_file(files, "gradle/init.d/" + child.name, child)
    elif kind == "python":
        p = _pip_user_config()
        if p is not None:
            _config_file(files, "pip/pip.conf", p)
    return files


def _config_tar(files: dict[str, Path], *, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, path in files.items():
            # Verify again when reading. The Docker prep is an explicit trusted
            # operation, but a swapped config should not silently add symlinks.
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > _MAX_CONFIG_BYTES:
                raise ValueError("Benutzerkonfiguration wurde während des Lesens verändert.")
            data = path.read_bytes()
            if len(data) > _MAX_CONFIG_BYTES:
                raise ValueError("Benutzerkonfiguration überschreitet das Limit.")
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.uid = member.gid = 65532
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        for name, data in (extra or {}).items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.uid = member.gid = 65532
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def _check(result, stage: str) -> None:
    if result.returncode:
        # Avoid echoing credentials possibly contained in Maven/Gradle/pip logs.
        raise RuntimeError(f"Docker-Prepare fehlgeschlagen: {stage} (Exit {result.returncode}).")


def _docker_run(backend: DockerBackend, arguments: list[str], timeout: int, *, data: bytes | None = None) -> None:
    _check(backend.run(arguments, timeout=timeout, input_bytes=data), arguments[0])


def _copy_cache_archive(
    backend: DockerBackend,
    container: str,
    source_dir: str,
    host_dir: Path,
    *,
    timeout: int,
) -> None:
    """Extract a bounded Docker TAR only after verifying every member.

    Do not use tarfile.extractall, docker cp, or accept symlinks/hardlinks.
    Never include user configuration or project source in the returned archive.
    """
    command = backend.command("exec", container, "tar", "-C", source_dir, "-cf", "-", ".")
    with tempfile.TemporaryFile() as archive_file:
        completed = subprocess.run(  # nosec B603
            command,
            stdout=archive_file,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError("Docker-Prepare konnte den Cache nicht exportieren.")
        archive_file.seek(0)
        total_bytes = 0
        count = 0
        with tarfile.open(fileobj=archive_file, mode="r|") as archive:
            for member in archive:
                count += 1
                total_bytes += max(member.size, 0)
                if count > _MAX_RETURN_FILES or total_bytes > _MAX_RETURN_BYTES:
                    raise ValueError("Docker-Cache überschreitet das Sicherheitslimit.")
                name = member.name.removeprefix("./")
                if not name or name == ".":
                    continue
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or any(part in {"", "."} for part in path.parts)
                ):
                    raise ValueError("Ungültiger Pfad im Docker-Cache.")
                dest = host_dir.joinpath(*path.parts)
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists() or dest.is_symlink():
                        raise ValueError("Doppelter Eintrag im Docker-Cache.")
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError("Ungültige Cache-Datei.")
                    with dest.open("xb") as target:
                        remaining = member.size
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Docker-Cache ist unvollständig.")
                            target.write(chunk)
                            remaining -= len(chunk)
                else:
                    raise ValueError("Docker-Cache enthält Symlinks oder Spezialdateien.")


def _image_policy(backend: DockerBackend, name: str) -> None:
    """Verify Docker isolation settings, separately from the stricter MCP sandbox."""
    result = backend.run(["inspect", name], timeout=30)
    _check(result, "inspect")
    try:
        obj = json.loads(result.stdout)[0]
        host = obj["HostConfig"]
        config = obj["Config"]
        mounts = obj.get("Mounts", [])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Docker-Prepare konnte die Containerpolicy nicht prüfen.") from exc
    if not (
        host.get("NetworkMode") == "bridge"
        and host.get("PidMode") != "host"
        and host.get("IpcMode") != "host"
        and host.get("UTSMode") != "host"
        and any(str(v).startswith("no-new-privileges") for v in (host.get("SecurityOpt") or []))
        and host.get("ReadonlyRootfs") is True
        and host.get("Privileged") is False
        and host.get("Binds") in (None, [])
        and config.get("User") == "65532:65532"
        and host.get("Tmpfs", {}).get("/tmp") is not None
        and host.get("Tmpfs", {}).get("/work") is not None
        and any(str(v).lower() == "all" for v in (host.get("CapDrop") or []))
        and not config.get("Volumes")
        and all(m.get("Type") == "tmpfs" and m.get("Destination") in {"/tmp", "/work"} for m in mounts)
    ):
        raise RuntimeError("Docker-Prepare entspricht nicht der erwarteten Containerpolicy.")


def prepare_in_docker(
    kind: str,
    project: Path,
    cache_root: Path,
    *,
    image: str,
    timeout: int = 1800,
    project_identity: str | None = None,
    use_user_config: bool = True,
    gradle_user_home: Path | None = None,
    wsl: bool = False,
    wsl_distribution: str | None = None,
) -> MavenCacheEntry | GradleCacheEntry | PythonCacheEntry:
    if kind not in {"maven", "gradle", "python"}:
        raise ValueError("Ungültiges Buildsystem.")
    if not image or image.strip() != image or image.startswith("-") or any(c.isspace() for c in image):
        raise ValueError("--image muss eine gültige, nicht leere Docker-Image-Referenz sein.")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")
    project = project.expanduser().resolve()
    root = cache_root.expanduser().resolve()
    if kind == "python":
        # Local paths outside the project are not available in Docker prepare.
        plan = python_dependency_plan(project, allow_local_sources=False)
        entry = python_cache_entry(root, project, project_identity=project_identity)
    elif kind == "maven":
        entry = cache_entry(root, project, project_identity=project_identity)
    else:
        entry = gradle_cache_entry(root, project, project_identity=project_identity)

    root.mkdir(parents=True, exist_ok=True)
    if entry.directory.is_symlink():
        raise ValueError("Cache-Eintrag darf kein Symlink sein.")
    config = _user_configuration(
        kind, gradle_user_home=gradle_user_home, include_user_config=use_user_config
    )
    extra: dict[str, bytes] = {}
    if kind == "gradle":
        # Import lazily: cache_cli calls this module, and owns the existing script.
        from .cache_cli import _write_gradle_runtime_resolver
        with tempfile.TemporaryDirectory() as script_dir:
            extra["gradle/resolver.gradle"] = _write_gradle_runtime_resolver(
                Path(script_dir)
            ).read_bytes()
    backend = DockerBackend(wsl=wsl, wsl_distribution=wsl_distribution)
    name = "cli-agent-prepare-" + uuid.uuid4().hex
    temporary = Path(tempfile.mkdtemp(prefix=f".{entry.key}-", dir=root))
    # docker create may reach the daemon even if the CLI subsequently times out.
    # The unique name is known already, so always attempt cleanup in that case.
    created = True
    try:
        _docker_run(backend, [
            "create", "--name", name, "--pull", "never",
            "--user", "65532:65532", "--read-only",
            "--tmpfs", "/work:rw,nosuid,nodev,size=1g,uid=65532,gid=65532,mode=0700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=4g,uid=65532,gid=65532,mode=0700",
            "--network", "bridge", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "256", "--memory", "4g", "--cpus", "2",
            "--env", "HOME=/tmp/home", "--entrypoint", "sh",
            image, "-c",
            "mkdir -p /tmp/home /tmp/config /tmp/prepared; while :; do sleep 3600; done",
        ], 60)
        _image_policy(backend, name)
        _docker_run(backend, ["start", name], 60)

        snapshot = create_project_snapshot(
            project, max_file_bytes=32 * 1024 * 1024,
            max_project_bytes=512 * 1024 * 1024,
            max_snapshot_entries=40_000,
        )
        _docker_run(
            backend, ["exec", "-i", name, "tar", "-C", "/work", "-xf", "-"],
            _TRANSFER_TIMEOUT, data=snapshot.archive,
        )
        if config or extra:
            _docker_run(
                backend, ["exec", "-i", name, "tar", "-C", "/tmp/config", "-xf", "-"],
                _TRANSFER_TIMEOUT, data=_config_tar(config, extra=extra),
            )
        command: list[str]
        destination: Path
        archive_source: str
        if kind == "maven":
            if "maven/settings-security.xml" in config:
                _docker_run(
                    backend, ["exec", name, "sh", "-c",
                              "mkdir -p /tmp/home/.m2 && cp /tmp/config/maven/settings-security.xml /tmp/home/.m2/settings-security.xml"],
                    30,
                )
            settings = ["-s", "/tmp/config/maven/settings.xml"] if "maven/settings.xml" in config else []
            base = ["exec", "-w", "/work", name, "mvn", "-B", *settings, "-Dmaven.repo.local=/tmp/prepared/repository"]
            for goal in (["dependency:go-offline"], ["-DskipTests", "package"]):
                _docker_run(backend, [*base, *goal], timeout)
            destination = temporary / "repository"
            archive_source = "/tmp/prepared/repository"
        elif kind == "gradle":
            _docker_run(backend, ["exec", name, "sh", "-c",
                "mkdir -p /tmp/prepared/gradle-home && if test -d /tmp/config/gradle; then cp -R /tmp/config/gradle/. /tmp/prepared/gradle-home/; fi"], 30)
            _docker_run(backend, [
                "exec", "-w", "/work", name, "gradle", "--no-daemon",
                "--refresh-dependencies", "--gradle-user-home",
                "/tmp/prepared/gradle-home", "--init-script",
                "/tmp/config/gradle/resolver.gradle",
                "assemble", "testClasses", "_cliAgentResolveRuntimeDependencies",
            ], timeout)
            destination = temporary / "gradle-home" / "caches" / "modules-2"
            archive_source = "/tmp/prepared/gradle-home/caches/modules-2"
        else:
            command = ["exec", "-w", "/work", name, "python", "-m", "pip", "wheel",
                       "--disable-pip-version-check", "--wheel-dir",
                       "/tmp/prepared/wheels", "-r", "requirements.txt"]
            if "pip/pip.conf" in config:
                command = ["exec", "-e", "PIP_CONFIG_FILE=/tmp/config/pip/pip.conf",
                           "-w", "/work", name, *command[4:]]
            _docker_run(backend, command, timeout)
            destination = temporary / "wheels"
            archive_source = "/tmp/prepared/wheels"

        destination.mkdir(parents=True, exist_ok=True)
        _copy_cache_archive(
            backend, name, archive_source, destination, timeout=timeout,
        )
        if kind == "maven":
            sanitize_repository_for_offline_use(destination)
            write_ready_metadata(temporary, entry.key)
        elif kind == "gradle":
            sanitize_gradle_home_for_promotion(temporary / "gradle-home")
            write_gradle_ready_metadata(temporary, entry.key)
        else:
            python_info = backend.run([
                "exec", name, "python", "-c",
                "import json,platform;print(json.dumps({'python_version':platform.python_version(),'python_implementation':platform.python_implementation(),'machine':platform.machine()}))",
            ], timeout=30)
            _check(python_info, "python metadata")
            metadata = json.loads(python_info.stdout)
            write_python_ready_metadata(
                temporary, entry.key, plan, interpreter_metadata=metadata,
                preparation_environment="docker",
            )
        if entry.directory.exists():
            import shutil
            shutil.rmtree(entry.directory)
        temporary.replace(entry.directory)
        return entry
    finally:
        if created:
            try:
                backend.run(["rm", "-f", name], timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if temporary.exists():
            import shutil
            shutil.rmtree(temporary, ignore_errors=True)
