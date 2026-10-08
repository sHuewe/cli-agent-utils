# cli-agent-utils

Independently installable MCP servers and reusable [cli-agent](https://github.com/sHuewe/cli-agent) flows.

This repository is a **monorepo, not a combined MCP distribution**. Each MCP server has its own `pyproject.toml`, dependencies, console entry points, tests, and security documentation.

## Contents

| Project | Python distribution | Executables |
| --- | --- | --- |
| [Docker Compose MCP](mcp/compose/README.md) | `cli-agent-compose-mcp` | `cli-agent-compose-mcp` |
| [Sandbox Test Validator MCP](mcp/test-validator/README.md) | `cli-agent-test-validator-mcp` | `cli-agent-test-validator-mcp`, `cli-agent-test-cache` |
| [Flows](flow/) | Not a Python package | TOML workflows and prompts |

The legacy Python build/start validator and its `validate_python_project` tool have been **removed**. The Test Validator supports Python tests and Java builds/tests but does not duplicate that legacy Python application-start functionality.

## Install one server only

From a checkout, install only the approved server into an isolated environment:

```bash
pipx install ./mcp/compose
# or
pipx install ./mcp/test-validator
```

From GitHub, pin a reviewed commit or tag:

```bash
pipx install "git+https://github.com/sHuewe/cli-agent-utils.git@<reviewed-ref>#subdirectory=mcp/compose"
pipx install "git+https://github.com/sHuewe/cli-agent-utils.git@<reviewed-ref>#subdirectory=mcp/test-validator"
```

Only the selected distribution and its declared dependencies are installed. The Git client may nevertheless **fetch the complete repository**. For strict enterprise artifact review, publish and approve each project's wheel separately. Software installation does not itself authorize running Docker or MCP tools.

The previously used commands are preserved (except the removed `cli-agent-python-validator-mcp`). The Test Validator's `cli-agent-test-cache` command also stays in its package; `prepare-python` must still run within WSL using Linux Python when applicable.

## Development

The root `pyproject.toml` defines an optional, non-installable **uv workspace**. It is not a metapackage that installs every MCP:

```bash
uv sync --all-packages
uv run --all-packages pytest mcp/
```

You can also develop and test each distribution without uv (run in separate virtual environments):

```bash
python -m pip install -e "./mcp/compose[dev]"
python -m pytest mcp/compose/tests
```

```bash
python -m pip install -e "./mcp/test-validator[dev]"
python -m pytest mcp/test-validator/tests
```

The GitHub Actions workflow tests each distribution in a **fresh, isolated** environment to catch missing or accidental cross-package dependencies.

## Workflows

`flow/` remains a collection of self-contained cli-agent flow-runner configurations and prompts, including `flow/okf/`. It is not a Python package and is not installed with an MCP server.

See [architecture, packaging and migration](docs/architecture.md), the [Compose README](mcp/compose/README.md), and the [Test Validator documentation](mcp/test-validator/README.md).
