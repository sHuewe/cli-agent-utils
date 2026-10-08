# Docker Compose MCP

Standalone install:

```bash
pipx install ./mcp/compose
```


The Compose MCP is intentionally outside the `cli-agent` core because Docker daemon access is a privileged host boundary and is unnecessary for most agent use cases.

The server is scoped to the directory supplied with `--project-directory`. It accepts only one of the standard Compose filenames in that directory and rejects a Compose file that resolves outside it. Docker commands use fixed argv lists without a shell. Service names are validated against `docker compose config --services` before log or mutation commands are executed.

Read-only tools are `get_compose_file`, `compose_ps` and `compose_logs`. `--allow-modify-services` additionally exposes `compose_up_all`, `compose_up`, `compose_down` and `compose_restart`. `--wsl` invokes Docker through WSL.

Example:

```text
cli-agent-compose-mcp --project-directory C:\dev\project
```

Mutating variant:

```text
cli-agent-compose-mcp --project-directory C:\dev\project --allow-modify-services
```
