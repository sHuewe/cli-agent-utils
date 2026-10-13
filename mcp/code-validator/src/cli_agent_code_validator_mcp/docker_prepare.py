"""Explicitly user-invoked Python wheel preparation using a temporary Docker container.

This is NOT an MCP tool and is NOT the offline code-validator sandbox. The
operator trusts the requirements/build backends and any pip credentials passed
to the bridge-networked container. Only requirements/constraints files are
copied from the project, and only wheel files are returned to the host cache.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .code_validator_snapshot import _open_verified_regular_file
from .docker_backend import DockerBackend
from .python_cache import (
    PythonCacheEntry,
    _requirement_files,
    python_cache_entry,
    python_dependency_plan,
    write_python_ready_metadata,
)

_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_REQUIREMENTS_BYTES = 64 * 1024 * 1024
_MAX_REQUIREMENTS_FILES = 256
_MAX_WHEEL_ARCHIVE_BYTES = 1024 * 1024 * 1024
_MAX_WHEEL_FILES = 10000
_TRANSFER_TIMEOUT = 300


def _pip_user_config() -> Path | None:
    """Select one explicit or user pip config, never the full user directory."""
    override = os.environ.get("PIP_CONFIG_FILE")
    if override is not None:
        if override.casefold() in {os.devnull.casefold(), "/dev/null", "nul"}:
            return None
        if override:
            explicit = Path(override).expanduser()
            # pip suppresses user config only if its explicit config exists.
            # Preserve a symlink here so _pip_config_snapshot can reject it.
            if explicit.is_file() or explicit.is_symlink():
                return explicit
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        candidates = (
            *((Path(appdata) / "pip" / "pip.ini",) if appdata else ()),
            home / "pip" / "pip.ini",
        )
        return next((p for p in candidates if p.is_file() or p.is_symlink()), None)
    if sys.platform == "darwin":
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            mac_config = Path(xdg_data_home).expanduser() / "pip" / "pip.conf"
            if mac_config.parent.is_dir() and (
                mac_config.is_file() or mac_config.is_symlink()
            ):
                return mac_config
            # With XDG_DATA_HOME set, pip does not use Library/Application
            # Support as a fallback; it checks ~/.config and the legacy path.
        else:
            mac_config = home / "Library" / "Application Support" / "pip" / "pip.conf"
            if mac_config.is_file() or mac_config.is_symlink():
                return mac_config
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_home).expanduser() if xdg_home else home / ".config"
    candidates = (config_home / "pip" / "pip.conf", home / ".pip" / "pip.conf")
    return next((p for p in candidates if p.is_file() or p.is_symlink()), None)


def _regular_file_bytes(path: Path, *, limit: int) -> bytes:
    """Re-check source identity while opening, rejecting link/reparse substitution."""
    expected = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(expected.st_mode) or expected.st_size > limit:
        raise ValueError("Datei ist nicht regulär oder überschreitet das Größenlimit.")
    handle, opened = _open_verified_regular_file(path, expected)
    with handle:
        data = handle.read(limit + 1)
    if len(data) > limit or len(data) != opened.st_size:
        raise ValueError("Datei wurde verändert oder überschreitet das Größenlimit.")
    return data


def _files_tar(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.uid = member.gid = 65532
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def _requirements_snapshot(project: Path) -> bytes:
    """Archive ONLY root requirements and recursively included -r/-c files."""
    selected = _requirement_files(project, allow_local_sources=False)
    if len(selected) > _MAX_REQUIREMENTS_FILES:
        raise ValueError("Zu viele Requirements-Dateien für Docker-Prepare.")
    contents: dict[str, bytes] = {}
    total = 0
    for path in selected:
        relative = path.relative_to(project).as_posix()
        if relative.startswith("../") or relative.startswith("/"):
            raise ValueError("Requirements-Datei liegt außerhalb des Projekts.")
        data = _regular_file_bytes(path, limit=16 * 1024 * 1024)
        total += len(data)
        if total > _MAX_REQUIREMENTS_BYTES:
            raise ValueError("Requirements überschreiten das Größenlimit.")
        contents[relative] = data
    return _files_tar(contents)


def _pip_config_snapshot(*, include_user_config: bool) -> bytes | None:
    if not include_user_config:
        return None
    path = _pip_user_config()
    if path is None:
        return None
    if path.is_symlink():
        raise ValueError("pip-Konfiguration darf kein Symlink sein.")
    if not path.exists():
        return None
    return _files_tar({"pip/pip.conf": _regular_file_bytes(path, limit=_MAX_CONFIG_BYTES)})


def _check(result, stage: str) -> None:
    if result.returncode != 0:
        # Never echo potentially credential-bearing pip/build output.
        raise RuntimeError(f"Docker-Prepare fehlgeschlagen: {stage} (Exit {result.returncode}).")


def _docker_run(
    backend: DockerBackend,
    args: list[str],
    timeout: int,
    *,
    data: bytes | None = None,
) -> None:
    _check(backend.run(args, timeout=timeout, input_bytes=data), args[0])


def _image_policy(backend: DockerBackend, name: str) -> None:
    result = backend.run(["inspect", name], timeout=30)
    _check(result, "inspect")
    try:
        payload = json.loads(result.stdout)
        host = payload[0]["HostConfig"]
        config = payload[0]["Config"]
        mounts = payload[0].get("Mounts", [])
        tmpfs = host.get("Tmpfs") or {}
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Docker-Prepare konnte Container-Einstellungen nicht prüfen.") from exc
    if not (
        isinstance(payload, list) and len(payload) == 1
        and host.get("NetworkMode") == "bridge"
        and host.get("PidMode") != "host"
        and host.get("IpcMode") != "host"
        and host.get("UTSMode") != "host"
        and host.get("ReadonlyRootfs") is True
        and host.get("Privileged") is False
        and not host.get("Binds")
        and config.get("User") == "65532:65532"
        and "/tmp" in tmpfs and "/work" in tmpfs
        and any(str(v).lower() == "all" for v in (host.get("CapDrop") or []))
        and any(str(v).startswith("no-new-privileges") for v in (host.get("SecurityOpt") or []))
        and not config.get("Volumes")
        and all(
            isinstance(m, dict) and m.get("Type") == "tmpfs"
            and m.get("Destination") in {"/tmp", "/work"}
            for m in mounts
        )
    ):
        raise RuntimeError("Docker-Prepare entspricht nicht der erwarteten Containerpolicy.")


def _extract_wheel_archive(archive_file, destination: Path) -> None:
    """Reject paths, symlinks, special files and non-wheel cache output."""
    total = 0
    count = 0
    with tarfile.open(fileobj=archive_file, mode="r|") as archive:
        for member in archive:
            if member.name in {".", "./"}:
                if not member.isdir():
                    raise ValueError("Ungültiger Docker-Cache-Eintrag.")
                continue
            name = member.name.removeprefix("./")
            if (
                not name or name in {".", ".."} or "/" in name
                or "\\" in name or ":" in name
                or any(ord(char) < 32 for char in name)
                or not name.endswith(".whl")
                or not member.isfile()
            ):
                raise ValueError("Docker-Cache enthält ungültige Dateien oder Pfade.")
            count += 1
            total += member.size
            if count > _MAX_WHEEL_FILES or total > _MAX_WHEEL_ARCHIVE_BYTES:
                raise ValueError("Docker-Wheel-Cache überschreitet das Limit.")
            if (destination / name).exists() or (destination / name).is_symlink():
                raise ValueError("Doppeltes Wheel im Docker-Cache.")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Docker-Wheel-Cache ist ungültig.")
            with (destination / name).open("xb") as target:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Docker-Wheel-Cache ist unvollständig.")
                    target.write(chunk)
                    remaining -= len(chunk)


def _copy_wheels(
    backend: DockerBackend, container: str, destination: Path, *, timeout: int,
) -> None:
    """Enforce transfer size and timeout *during* Docker archive streaming."""
    command = backend.command(
        "exec", container, "tar", "-C", "/tmp/prepared/wheels", "-cf", "-", "."
    )
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(  # nosec B603
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        assert process.stdout is not None

        def transfer() -> None:
            size = 0
            with process.stdout:
                while True:
                    chunk = process.stdout.read(1024 * 1024)
                    if not chunk:
                        return
                    size += len(chunk)
                    if size > _MAX_WHEEL_ARCHIVE_BYTES + 1024 * 1024:
                        raise ValueError("Docker-Archiv überschreitet das Transferlimit.")
                    output.write(chunk)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(transfer)
            try:
                future.result(timeout=timeout)
                status = process.wait(timeout=30)
                if status != 0:
                    raise RuntimeError("Docker-Prepare konnte die Wheels nicht exportieren.")
            except BaseException:
                if process.poll() is None:
                    process.kill()
                process.wait()
                raise
        output.seek(0)
        _extract_wheel_archive(output, destination)


def _promote_cache(temporary: Path, final: Path) -> None:
    """Retain previous ready cache if replacing it fails."""
    backup = final.parent / f".{final.name}-backup-{uuid.uuid4().hex}"
    old_exists = final.exists()
    if final.is_symlink():
        raise ValueError("Cache-Ziel darf kein Symlink sein.")
    if old_exists:
        final.rename(backup)
    try:
        temporary.rename(final)
    except BaseException:
        if old_exists:
            backup.rename(final)
        raise
    if old_exists:
        shutil.rmtree(backup)


def prepare_python_in_docker(
    project: Path,
    cache_root: Path,
    *,
    image: str,
    timeout: int = 1800,
    project_identity: str | None = None,
    use_user_config: bool = True,
    wsl: bool = False,
    wsl_distribution: str | None = None,
) -> PythonCacheEntry:
    """Explicit operator action; never exposed through MCP."""
    if not image or image.strip() != image or image.startswith("-") or any(ch.isspace() for ch in image):
        raise ValueError("--image muss eine gültige Docker-Image-Referenz sein.")
    if timeout <= 0:
        raise ValueError("--timeout muss positiv sein.")
    project = project.expanduser().resolve()
    plan = python_dependency_plan(project, allow_local_sources=False)
    requirements_archive = _requirements_snapshot(project)
    config_archive = _pip_config_snapshot(include_user_config=use_user_config)
    root = cache_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    entry = python_cache_entry(root, project, project_identity=project_identity)
    if entry.directory.is_symlink():
        raise ValueError("Cache-Eintrag darf kein Symlink sein.")
    backend = DockerBackend(wsl=wsl, wsl_distribution=wsl_distribution)
    name = "cli-agent-prepare-" + uuid.uuid4().hex
    temporary = Path(tempfile.mkdtemp(prefix=f".{entry.key}-", dir=root))
    try:
        # Even after a CLI timeout Docker may already have created the container.
        _docker_run(backend, [
            "create", "--name", name, "--pull", "never",
            "--user", "65532:65532", "--read-only",
            "--tmpfs", "/work:rw,nosuid,nodev,size=64m,uid=65532,gid=65532,mode=0700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=4g,uid=65532,gid=65532,mode=0700",
            "--network", "bridge", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "256", "--memory", "4g", "--cpus", "2",
            "--env", "HOME=/tmp/home", "--entrypoint", "sh",
            image, "-c",
            "mkdir -p /tmp/home /tmp/config /tmp/prepared/wheels; while :; do sleep 3600; done",
        ], 60)
        _image_policy(backend, name)
        _docker_run(backend, ["start", name], 60)
        _docker_run(
            backend, ["exec", "-i", name, "tar", "-C", "/work", "-xf", "-"],
            _TRANSFER_TIMEOUT, data=requirements_archive,
        )
        command = ["exec", "-w", "/work", name, "python", "-m", "pip",
                   "wheel", "--disable-pip-version-check",
                   "--wheel-dir", "/tmp/prepared/wheels", "-r", "requirements.txt"]
        if config_archive is not None:
            _docker_run(
                backend, ["exec", "-i", name, "tar", "-C", "/tmp/config", "-xf", "-"],
                _TRANSFER_TIMEOUT, data=config_archive,
            )
            command = ["exec", "-e", "PIP_CONFIG_FILE=/tmp/config/pip/pip.conf",
                       "-w", "/work", name, *command[4:]]
        _docker_run(backend, command, timeout)
        wheels = temporary / "wheels"
        wheels.mkdir()
        _copy_wheels(backend, name, wheels, timeout=timeout)
        info = backend.run([
            "exec", name, "python", "-c",
            "import json,platform;print(json.dumps({'python_version':platform.python_version(),'python_implementation':platform.python_implementation(),'machine':platform.machine()}))",
        ], timeout=30)
        _check(info, "Python metadata")
        write_python_ready_metadata(
            temporary, entry.key, plan,
            interpreter_metadata=json.loads(info.stdout),
            preparation_environment="docker",
        )
        _promote_cache(temporary, entry.directory)
        return entry
    finally:
        try:
            backend.run(["rm", "-f", name], timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
