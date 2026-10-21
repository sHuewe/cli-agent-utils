from __future__ import annotations

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .compose import ComposeProject


def create_server(project: ComposeProject, *, allow_modify_services: bool = False) -> FastMCP:
    mcp = FastMCP(
        "Docker Compose",
        instructions=(
            "Use these tools only for the Docker Compose project fixed when this server started. "
            "Inspect the Compose file, service status, and logs when information is missing. "
            "Never invent service names. Service-control tools have real effects: only start, "
            "stop, or restart services when the user requested that action."
        ),
    )

    @mcp.tool()
    def get_compose_file() -> str:
        """Return the Compose YAML selected at server startup."""
        return project.read_compose_file()

    @mcp.tool()
    def compose_ps() -> str:
        """Show the current status of services in the selected Compose project."""
        return project.ps()

    if allow_modify_services:
        @mcp.tool()
        def compose_up_all() -> str:
            """Start all services of the Docker Compose project."""
            return project.up_all()

        @mcp.tool()
        def compose_up(service_name: str) -> str:
            """Start exactly one Docker Compose service."""
            return project.start(service_name)

        @mcp.tool()
        def compose_down(service_name: str) -> str:
            """Stop exactly one Docker Compose service."""
            return project.stop(service_name)

        @mcp.tool()
        def compose_restart(service_name: str) -> str:
            """Restart exactly one Docker Compose service."""
            return project.restart(service_name)

    @mcp.tool()
    def compose_logs(service_name: str) -> str:
        """Return the last 200 log lines for one service."""
        return project.logs(service_name)

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP server for Docker Compose tools")
    parser.add_argument("--project-directory", required=True, type=Path)
    parser.add_argument("--allow-modify-services", action="store_true")
    parser.add_argument("--wsl", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = ComposeProject.from_directory(args.project_directory, wsl=args.wsl)
    create_server(project, allow_modify_services=args.allow_modify_services).run(transport="stdio")


if __name__ == "__main__":
    main()
