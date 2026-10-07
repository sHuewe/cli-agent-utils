from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class TestValidationError(RuntimeError):
    """A test-validator request or sandbox setup is invalid."""


_IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$", re.IGNORECASE)


def is_pinned_image(image: str) -> bool:
    return bool(_IMAGE_DIGEST.fullmatch(image.strip()))


@dataclass(frozen=True)
class TestValidatorSettings:
    python_image: str
    maven_image: str
    gradle_image: str
    test_timeout_seconds: int = 180
    setup_timeout_seconds: int = 60
    memory_limit: str = "2g"
    cpu_limit: str = "2.0"
    pids_limit: int = 256
    work_tmpfs_size: str = "1g"
    tmp_tmpfs_size: str = "512m"
    max_project_bytes: int = 64 * 1024 * 1024
    max_file_bytes: int = 16 * 1024 * 1024
    max_snapshot_entries: int = 20_000
    max_output_chars: int = 200_000
    maven_cache_root: Path | None = None
    gradle_cache_root: Path | None = None
    python_cache_root: Path | None = None

    def __post_init__(self) -> None:
        for name, image in (
            ("python_image", self.python_image),
            ("maven_image", self.maven_image),
            ("gradle_image", self.gradle_image),
        ):
            if not image.strip():
                raise ValueError(f"{name} darf nicht leer sein.")
            if not is_pinned_image(image):
                raise ValueError(
                    f"{name} muss einen vollständigen sha256-Digest enthalten."
                )
        if self.test_timeout_seconds <= 0 or self.setup_timeout_seconds <= 0:
            raise ValueError("Timeouts müssen positiv sein.")
        if self.pids_limit <= 0:
            raise ValueError("pids_limit muss positiv sein.")
        if self.max_project_bytes <= 0 or self.max_file_bytes <= 0:
            raise ValueError("Projekt- und Dateigrößenlimits müssen positiv sein.")
        if self.max_snapshot_entries <= 0:
            raise ValueError("max_snapshot_entries muss positiv sein.")
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars muss positiv sein.")
        if self.maven_cache_root is not None:
            object.__setattr__(
                self,
                "maven_cache_root",
                self.maven_cache_root.expanduser().resolve(),
            )
        if self.gradle_cache_root is not None:
            object.__setattr__(
                self,
                "gradle_cache_root",
                self.gradle_cache_root.expanduser().resolve(),
            )
        if self.python_cache_root is not None:
            object.__setattr__(
                self,
                "python_cache_root",
                self.python_cache_root.expanduser().resolve(),
            )
