# Sandbox Test Validator MCP

The Sandbox Test Validator runs Python and Java test suites in a short-lived Docker container while keeping the real `cli-agent` workspace outside that container.

## Tools

The MCP exposes exactly:

- `run_python_tests(project_path=".", test_selector=None)`
- `run_java_tests(project_path=".", test_selector=None, build_system="auto")`

There is no arbitrary command, shell, Docker or package-install tool in the MCP contract.

## Workspace permission

The server consumes the Core-owned runtime variables:

```text
CLI_AGENT_WORKSPACE_ACCESS
CLI_AGENT_WORKSPACE_DIRECTORY
```

Startup requires access `read` or `write`. The recommended admin policy is therefore:

```toml
required_workspace_access = "read"
```

A run without `--with-os-read` / `--with-os-write`, or a flow step with `workspace_access = "none"`, will not start the server.

The validator treats the workspace as a source for the snapshot only. It never writes the real workspace.

## Snapshot rules

The selected `project_path` must be relative to the fixed workspace and cannot contain `..`.

The snapshot is created entirely in memory. No host-side temporary source directory or TAR file is created.

The snapshot:

- includes ordinary project files, including `.env` when present,
- omits common generated/cache directories such as `.git`, `.venv`, `target`, `build`, `dist`, `.gradle`, `node_modules` and `.cli-agent`,
- rejects symlinks,
- rejects sockets, devices, FIFOs and other non-regular filesystem entries,
- applies per-file and total-project size limits.

The TAR entries are written with container UID/GID `65532:65532`.

## Docker sandbox

The validator first creates the container and inspects its effective configuration before it starts project code.

Required properties include:

- network mode `none`,
- root filesystem read-only,
- user `65532:65532`,
- all capabilities dropped,
- `no-new-privileges`,
- not privileged,
- no host bind mounts,
- no unexpected image/volume mounts,
- `/tmp` and `/work` as tmpfs.

Project data is then streamed into `/work` through `docker cp -`; the real workspace is never mounted.

The Docker socket is never mounted into the test container.

The container is removed after the test run.

Docker is a strong practical isolation layer but not a virtual-machine security boundary. Native Linux containers still share the host kernel.

## Images and dependencies

All images must be digest-pinned and already present locally. `--pull never` is mandatory.

### Python

The configured Python image must already contain:

- Python,
- pytest,
- the dependencies needed by the project.

The validator deliberately does not run `pip install` and has no network access.

### Maven

The Maven image must contain Maven. Offline dependencies/plugins can be baked into `/opt/cli-agent-test-cache/maven`. Before the test, this seed cache is copied into writable tmpfs at `/tmp/m2`. The validator runs:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 test
```

or, with a selector:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -Dtest=<selector> test
```

### Gradle

The Gradle image must contain Gradle. Offline dependencies/plugins can be baked into `/opt/cli-agent-test-cache/gradle`. Before the test, this seed cache is copied into writable tmpfs at `/tmp/gradle`. The validator runs:

```text
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test
```

or:

```text
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test --tests <selector>
```

Dependency preparation that requires network access or credentials should be performed separately in a trusted preparation pipeline. The resulting test image may contain dependency caches, but should not contain credentials.

## Output and secret handling

Container stdout/stderr is bounded before being returned to the model.

Before testing, the validator scans common text configuration formats such as `.env`, `.properties`, YAML, JSON and TOML for values under sensitive keys including password, secret, token and API/access key names. Exact discovered values are redacted from returned output. Generic bearer-token, credential-assignment and PEM-private-key patterns are also redacted.

This protects against common accidental leakage. It does not protect against malicious test code deliberately transforming a secret before printing it.

Network exfiltration from the test container is blocked by `--network none`.

## Native Docker configuration

Example machine-wide `admin_config.toml`:

```toml
[[mcp.trusted_servers]]
name = "test-validator"
transport = "stdio"
command = "C:/absolute/path/to/cli-agent-test-validator-mcp.exe"
required_workspace_access = "read"
trust_instructions = false
args = [
    "--python-image", "registry.internal/python-tests@sha256:<digest>",
    "--maven-image", "registry.internal/maven-tests@sha256:<digest>",
    "--gradle-image", "registry.internal/gradle-tests@sha256:<digest>",
]
```

Project/user config:

```toml
[[mcp_servers]]
name = "test-validator"
```

Run with:

```text
cli-agent --with-os-read ...
```

## Docker through WSL

Add `--wsl`. Optionally select the distribution:

```toml
args = [
    "--python-image", "registry.internal/python-tests@sha256:<digest>",
    "--maven-image", "registry.internal/maven-tests@sha256:<digest>",
    "--gradle-image", "registry.internal/gradle-tests@sha256:<digest>",
    "--wsl",
    "--wsl-distribution", "Ubuntu",
]
```

The MCP process remains a normal stdio child of `cli-agent`; only Docker CLI calls are routed through WSL.

## Optional resource limits

The server supports administrator-controlled settings:

```text
--test-timeout 180
--setup-timeout 60
--memory-limit 2g
--cpu-limit 2.0
--pids-limit 256
--work-tmpfs-size 1g
--tmp-tmpfs-size 512m
--max-project-bytes 67108864
--max-file-bytes 16777216
--max-output-chars 200000
```

These are launch-time administrator settings, not MCP tool arguments, so the model cannot relax them.
