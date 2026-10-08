# Independent MCP distributions and migration

## Packaging boundaries

The repository contains two independent Python distributions:

* `mcp/compose` is `cli-agent-compose-mcp` with the `cli_agent_compose_mcp` namespace.
* `mcp/code-validator` is `cli-agent-code-validator-mcp` with the `cli_agent_code_validator_mcp` namespace. The `cli-agent-dependency-cache` command is part of this same distribution.

Every server has its own `pyproject.toml`, Python runtime dependencies, tests, documentation, and entry points. The root `pyproject.toml` is a **non-package uv workspace** for development, not an installable umbrella distribution. The `flow/` hierarchy remains standalone and does not require package installation.

## Migration from cli-agent-mcp

The previous umbrella distribution `cli-agent-mcp` installed all commands together. Before installing replacements, uninstall it:

```bash
pipx uninstall cli-agent-mcp
pipx install ./mcp/compose
pipx install ./mcp/code-validator
```

Install **only the distribution(s) approved for use**. If using regular pip, substitute `python -m pip uninstall cli-agent-mcp` and `python -m pip install ./mcp/<project>`. The old `cli-agent-python-validator-mcp` and its MCP tool `validate_python_project` were removed entirely. The newer Code-Validator does not implement the legacy Python application-start check.

The Compose command stays unchanged; the former Test Validator MCP executable is renamed from `cli-agent-test-validator-mcp` to `cli-agent-code-validator-mcp`. The former `cli-agent-test-cache` command is renamed to `cli-agent-dependency-cache`; existing installations and scripts must update that command name. The three Code-Validator MCP tool names remain `run_python_tests`, `run_java_build` and `run_java_tests`.

## Security and approvals

Review and approve each distribution and its transitive dependencies independently. Docker Compose control and Docker sandbox execution each expose different host-side risks; installing a package is not an authority boundary. The `cli-agent-dependency-cache` CLI performs explicit trusted host-side preparation with normal user build configuration and credentials; it must not become an LLM-callable tool by accident.

A `#subdirectory=` Git installation selects a distribution but can still clone the entire repo. For stricter source/artifact boundaries, use independently built wheels pinned to a reviewed revision. Preserve administrator control over cli-agent MCP server startup and Docker permissions.

See each server's README and the Code-Validator security documentation for runtime and threat-model specifics.

## Validation

The CI matrix installs each package separately in clean environments, executes its tests, builds a wheel, installs that wheel into a fresh virtual environment and checks console-script startup. It does not need a Docker daemon for mocked unit tests.
