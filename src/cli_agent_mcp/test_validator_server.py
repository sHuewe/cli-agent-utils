from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .docker_backend import DockerBackend
from .maven_cache import default_maven_cache_root
from .python_cache import default_python_cache_root
from .test_validator import DockerTestValidator
from .test_validator_types import TestValidationError, TestValidatorSettings

WORKSPACE_ACCESS_ENV = "CLI_AGENT_WORKSPACE_ACCESS"
WORKSPACE_DIRECTORY_ENV = "CLI_AGENT_WORKSPACE_DIRECTORY"


def _workspace_from_core_environment() -> Path:
    access = os.environ.get(WORKSPACE_ACCESS_ENV, "none")
    if access not in {"read", "write"}:
        raise TestValidationError(
            "Der Test-Validator benötigt vom cli-agent mindestens Workspace-Read-Zugriff."
        )
    workspace = os.environ.get(WORKSPACE_DIRECTORY_ENV)
    if not workspace:
        raise TestValidationError(
            "CLI_AGENT_WORKSPACE_DIRECTORY fehlt. Starte den MCP über einen "
            "aktuellen cli-agent Core mit --with-os-read oder --with-os-write."
        )
    return Path(workspace)


def create_server(validator: DockerTestValidator) -> FastMCP:
    mcp = FastMCP(
        "Sandbox Test Validator",
        instructions=(
            "Use run_python_tests for Python tests and run_java_tests for "
            "Maven/Gradle tests. Tests execute untrusted project code only "
            "inside a hardened no-network Docker sandbox. The real workspace "
            "is read but never mounted writable or modified by these tools. "
            "Treat success as test execution success, not as a proof of "
            "application security."
        ),
    )

    @mcp.tool()
    def run_python_tests(
        project_path: str = ".",
        test_selector: str | None = None,
    ) -> dict[str, Any]:
        """Run pytest in the isolated no-network test sandbox.

        project_path must be relative to the cli-agent workspace. test_selector
        may be a normal pytest node id such as tests/test_config.py::test_load.
        """
        return validator.run_python_tests(
            project_path=project_path,
            test_selector=test_selector,
        )

    @mcp.tool()
    def run_java_tests(
        project_path: str = ".",
        test_selector: str | None = None,
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> dict[str, Any]:
        """Run Maven or Gradle tests offline in the isolated Docker sandbox.

        Auto detection uses pom.xml or build.gradle/build.gradle.kts. A Java
        selector is translated to Maven -Dtest or Gradle --tests without
        exposing an arbitrary shell command.
        """
        return validator.run_java_tests(
            project_path=project_path,
            test_selector=test_selector,
            build_system=build_system,
        )

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MCP server for isolated Python and Java tests"
    )
    parser.add_argument(
        "--python-image",
        required=True,
        help="Pinned pytest-capable image reference with @sha256 digest",
    )
    parser.add_argument(
        "--maven-image",
        required=True,
        help="Pinned Maven image reference with @sha256 digest",
    )
    parser.add_argument(
        "--gradle-image",
        required=True,
        help="Pinned Gradle image reference with @sha256 digest",
    )
    parser.add_argument("--wsl", action="store_true")
    parser.add_argument(
        "--wsl-distribution",
        default=None,
        help="Optional WSL distribution used for the Docker CLI",
    )
    parser.add_argument("--test-timeout", type=int, default=180)
    parser.add_argument("--setup-timeout", type=int, default=60)
    parser.add_argument("--memory-limit", default="2g")
    parser.add_argument("--cpu-limit", default="2.0")
    parser.add_argument("--pids-limit", type=int, default=256)
    parser.add_argument("--work-tmpfs-size", default="1g")
    parser.add_argument("--tmp-tmpfs-size", default="512m")
    parser.add_argument(
        "--max-project-bytes",
        type=int,
        default=64 * 1024 * 1024,
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=16 * 1024 * 1024,
    )
    parser.add_argument("--max-output-chars", type=int, default=200_000)
    parser.add_argument(
        "--python-cache-root",
        type=Path,
        default=default_python_cache_root(),
        help=(
            "Shared root created by cli-agent-test-cache prepare-python "
            "(default: ~/.cli-agent/dependency-cache/python). "
            "Python cache preparation itself must run inside WSL."
        ),
    )
    parser.add_argument(
        "--maven-cache-root",
        type=Path,
        default=default_maven_cache_root(),
        help=(
            "Shared root created by cli-agent-test-cache prepare-maven "
            "(default: ~/.cli-agent/dependency-cache/maven). "
            "The validator selects a project dependency cache below this root "
            "by deterministic dependency key."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.wsl_distribution and not args.wsl:
        raise ValueError("--wsl-distribution benötigt --wsl.")
    workspace = _workspace_from_core_environment()
    settings = TestValidatorSettings(
        python_image=args.python_image,
        maven_image=args.maven_image,
        gradle_image=args.gradle_image,
        test_timeout_seconds=args.test_timeout,
        setup_timeout_seconds=args.setup_timeout,
        memory_limit=args.memory_limit,
        cpu_limit=args.cpu_limit,
        pids_limit=args.pids_limit,
        work_tmpfs_size=args.work_tmpfs_size,
        tmp_tmpfs_size=args.tmp_tmpfs_size,
        max_project_bytes=args.max_project_bytes,
        max_file_bytes=args.max_file_bytes,
        max_output_chars=args.max_output_chars,
        maven_cache_root=args.maven_cache_root,
        python_cache_root=args.python_cache_root,
    )
    backend = DockerBackend(
        wsl=args.wsl,
        wsl_distribution=args.wsl_distribution,
    )
    create_server(
        DockerTestValidator(workspace, settings, backend=backend)
    ).run(transport="stdio")


if __name__ == "__main__":
    main()
