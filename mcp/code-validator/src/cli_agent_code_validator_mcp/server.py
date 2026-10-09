from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from .docker_backend import DockerBackend
from .gradle_cache import default_gradle_cache_root
from .maven_cache import default_maven_cache_root
from .python_cache import default_python_cache_root
from .code_validator import DockerCodeValidator
from .code_validator_types import CodeValidationError, CodeValidatorSettings

WORKSPACE_ACCESS_ENV = "CLI_AGENT_WORKSPACE_ACCESS"
WORKSPACE_DIRECTORY_ENV = "CLI_AGENT_WORKSPACE_DIRECTORY"
CLI_AGENT_MESSAGE_TO_USER_META_KEY = (
    "io.github.shuewe.cli-agent/messageToUser"
)


def _tool_result(payload: dict[str, Any]) -> CallToolResult:
    """Split model-visible output from optional cli-agent user metadata."""
    model_payload = dict(payload)
    message_to_user = model_payload.pop("message_to_user", None)

    kwargs: dict[str, Any] = {
        "content": [
            TextContent(
                type="text",
                text=json.dumps(model_payload, ensure_ascii=False),
            )
        ]
    }

    fields = {
        *getattr(CallToolResult, "__annotations__", {}).keys(),
        *getattr(CallToolResult, "model_fields", {}).keys(),
        *getattr(CallToolResult, "__fields__", {}).keys(),
    }
    if "structuredContent" in fields:
        kwargs["structuredContent"] = model_payload
    elif "structured_content" in fields:
        kwargs["structured_content"] = model_payload

    if message_to_user is not None:
        if not isinstance(message_to_user, str) or not message_to_user.strip():
            raise CodeValidationError(
                "message_to_user muss ein nicht-leerer String sein."
            )
        metadata = {
            CLI_AGENT_MESSAGE_TO_USER_META_KEY: {
                "text": message_to_user,
            }
        }
        if "_meta" in fields:
            kwargs["_meta"] = metadata
        else:
            kwargs["meta"] = metadata

    return CallToolResult(**kwargs)


def _workspace_from_core_environment() -> Path:
    access = os.environ.get(WORKSPACE_ACCESS_ENV, "none")
    if access not in {"read", "write"}:
        raise CodeValidationError(
            "Der Code-Validator benötigt vom cli-agent mindestens Workspace-Read-Zugriff."
        )
    workspace = os.environ.get(WORKSPACE_DIRECTORY_ENV)
    if not workspace:
        raise CodeValidationError(
            "CLI_AGENT_WORKSPACE_DIRECTORY fehlt. Starte den MCP über einen "
            "aktuellen cli-agent Core mit --with-os-read oder --with-os-write."
        )
    return Path(workspace)


def create_server(validator: DockerCodeValidator) -> FastMCP:
    mcp = FastMCP(
        "Sandbox Code-Validator",
        instructions=(
            "For Java programming work, use run_java_build as the primary "
            "validation step after making code changes. Always try the build "
            "before considering Java test execution. If run_java_build "
            "succeeds, treat the implementation change as validated for normal "
            "programming tasks; do not run tests merely as an additional "
            "validation step. Use run_java_tests only when the task itself "
            "concerns test cases, for example when creating, modifying, "
            "debugging or explicitly verifying tests. Use run_python_tests "
            "likewise only for tasks that concern Python test cases; this "
            "server intentionally provides no generic Python build validator. "
            "Builds and tests execute untrusted project code only inside a "
            "hardened no-network Docker sandbox. The real workspace is read "
            "but never mounted writable or modified by these tools. A "
            "successful build or test run validates only that requested check, "
            "not application security."
        ),
    )

    @mcp.tool()
    def run_python_tests(
        project_path: str = ".",
        test_selector: str | None = None,
    ) -> CallToolResult:
        """Run pytest only when the task concerns Python test cases.

        Do not use this tool as a generic validation step after ordinary Python
        programming changes. Use it when creating, modifying, debugging or
        explicitly verifying Python tests. project_path must be relative to the
        cli-agent workspace. test_selector may be a normal pytest node id such
        as tests/test_config.py::test_load.
        """
        return _tool_result(
            validator.run_python_tests(
                project_path=project_path,
                test_selector=test_selector,
            )
        )

    @mcp.tool()
    def run_java_build(
        project_path: str = ".",
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> CallToolResult:
        """Primary validation tool after Java programming changes.

        Call this tool first after implementing Java/Maven/Gradle code changes.
        If it succeeds, consider the implementation validated for normal coding
        tasks and do not additionally run tests unless the task itself concerns
        test cases. Auto detection uses pom.xml or build.gradle/build.gradle.kts.
        Maven is fixed to package with -DskipTests; Gradle is fixed to the
        assemble task. Gradle project build logic may wire other tasks into
        assemble; that code still executes only inside the hardened sandbox.
        The model cannot supply arbitrary goals, tasks or command-line options.
        """
        return _tool_result(
            validator.run_java_build(
                project_path=project_path,
                build_system=build_system,
            )
        )

    @mcp.tool()
    def run_java_tests(
        project_path: str = ".",
        test_selector: str | None = None,
        build_system: Literal["auto", "maven", "gradle"] = "auto",
    ) -> CallToolResult:
        """Run Java tests only when the task itself concerns test cases.

        Do not use this tool as a generic validation step after ordinary Java
        programming changes. For Java code changes, call run_java_build first;
        a successful build is sufficient validation unless tests are part of
        the task. Use this tool when creating, modifying, debugging or
        explicitly verifying Java tests. Auto detection uses pom.xml or
        build.gradle/build.gradle.kts. A Java selector is translated to Maven
        -Dtest or Gradle --tests without exposing an arbitrary shell command.
        """
        return _tool_result(
            validator.run_java_tests(
                project_path=project_path,
                test_selector=test_selector,
                build_system=build_system,
            )
        )

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MCP server for isolated Python/Java tests and Java builds"
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
    parser.add_argument(
        "--max-snapshot-entries",
        type=int,
        default=20_000,
    )
    parser.add_argument("--max-output-chars", type=int, default=200_000)
    parser.add_argument(
        "--python-cache-root",
        type=Path,
        default=default_python_cache_root(),
        help=(
            "Shared root created by cli-agent-dependency-cache prepare-python "
            "(default: ~/.cli-agent/dependency-cache/python). "
            "Python cache preparation itself must run inside WSL."
        ),
    )
    parser.add_argument(
        "--gradle-cache-root",
        type=Path,
        default=default_gradle_cache_root(),
        help=(
            "Shared root created by cli-agent-dependency-cache prepare-gradle "
            "(default: ~/.cli-agent/dependency-cache/gradle)."
        ),
    )
    parser.add_argument(
        "--maven-cache-root",
        type=Path,
        default=default_maven_cache_root(),
        help=(
            "Shared root created by cli-agent-dependency-cache prepare-maven "
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
    settings = CodeValidatorSettings(
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
        max_snapshot_entries=args.max_snapshot_entries,
        max_output_chars=args.max_output_chars,
        maven_cache_root=args.maven_cache_root,
        gradle_cache_root=args.gradle_cache_root,
        python_cache_root=args.python_cache_root,
    )
    backend = DockerBackend(
        wsl=args.wsl,
        wsl_distribution=args.wsl_distribution,
    )
    create_server(
        DockerCodeValidator(workspace, settings, backend=backend)
    ).run(transport="stdio")


if __name__ == "__main__":
    main()
