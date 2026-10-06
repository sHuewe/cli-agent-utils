# cli-agent-mcp

Optional MCP servers for [`cli-agent`](https://github.com/sHuewe/cli-agent).

This repository contains MCP servers whose capabilities require Docker or other host-side execution surfaces that are intentionally kept outside the `cli-agent` core.

Currently included:

- **Docker Compose MCP**: inspect and optionally control a Compose project.
- **Python Validator MCP**: legacy build/start validation for Python projects.
- **Sandbox Test Validator MCP**: run Python/pytest and Java/Maven/Gradle tests in a hardened short-lived Docker sandbox.

## Installation

```powershell
py -m pipx install .
```

For development:

```powershell
python -m pip install -e ".[dev]"
pytest
```

Installed commands:

```text
cli-agent-compose-mcp
cli-agent-python-validator-mcp
cli-agent-test-validator-mcp
```

## Sandbox Test Validator MCP

The test validator is the recommended validator for automated code tests. It exposes only two model-visible tools:

```text
run_python_tests
run_java_tests
```

It does **not** expose an arbitrary shell or generic Docker command.

### Security model

The validator requires at least `workspace_access = "read"` from `cli-agent`. The workspace path and effective permission are supplied by the Core through the reserved environment variables:

```text
CLI_AGENT_WORKSPACE_ACCESS
CLI_AGENT_WORKSPACE_DIRECTORY
```

Do not configure these variables manually.

For every test run the validator:

- accepts only project-relative paths below the fixed workspace,
- creates the project snapshot as an in-memory TAR archive and streams it into the sandbox without a host-side temporary source file,
- rejects symlinks and non-regular filesystem entries,
- never bind-mounts the real workspace into the test container,
- creates disposable `/work`, `/tmp` and bounded `/output` tmpfs mounts,
- always uses Docker `--network none`,
- requires digest-pinned images and uses `--pull never`,
- runs as UID/GID `65532:65532`,
- uses a read-only container root filesystem,
- drops all capabilities and enables `no-new-privileges`,
- applies CPU, memory, PID, project-size, file-size, timeout and output limits,
- verifies the actual Docker container configuration with `docker inspect` before project code is copied or executed,
- redacts detected project secret values and common credential patterns before returning output to the LLM,
- removes the short-lived container after the run.

Project files such as `.env` are intentionally part of the project snapshot when they are present in the selected project. Test code can therefore read them. Network access is blocked, and direct output of detected secrets is redacted, but redaction is **not** a complete confidentiality boundary against deliberately transformed output.

### Required Docker images

Three immutable image references are configured administratively. Each image must provide a POSIX `sh`, `tar`, `cat`, `cp` and `mkdir` in addition to the language/build tooling:

- a Python image containing Python, `pytest` and all dependencies required for the tested projects,
- a Maven image containing Maven and the dependencies required for offline builds,
- a Gradle image containing Gradle and the dependencies required for offline builds.

Every reference must include a complete SHA-256 digest:

```text
registry.internal/python-tests@sha256:<64-hex-digest>
registry.internal/maven-tests@sha256:<64-hex-digest>
registry.internal/gradle-tests@sha256:<64-hex-digest>
```

The validator never downloads packages during a test. Python uses the environment already present in its image. Maven runs with `-o`; Gradle runs with `--offline`. Maven and Gradle images may seed offline caches at `/opt/cli-agent-test-cache/maven` and `/opt/cli-agent-test-cache/gradle`; these caches are copied into writable container tmpfs before the build starts. Prepare or refresh dependency images separately in a trusted preparation process with network access and credentials, then run tests offline.

The images must already exist in the Docker daemon because the validator uses `--pull never`.

### cli-agent admin configuration

With current `cli-agent`, external stdio launch configuration belongs in the machine-wide `admin_config.toml`. First determine the absolute executable path, for example on Windows:

```powershell
(Get-Command cli-agent-test-validator-mcp).Source
```

Then configure the trusted server:

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

For Docker through WSL, add:

```toml
args = [
    "--python-image", "registry.internal/python-tests@sha256:<digest>",
    "--maven-image", "registry.internal/maven-tests@sha256:<digest>",
    "--gradle-image", "registry.internal/gradle-tests@sha256:<digest>",
    "--wsl",
    "--wsl-distribution", "Ubuntu",
]
```

`--wsl-distribution` is optional. Without it, the default WSL distribution is used.

### cli-agent project/user configuration

The project/user config references only the administrator-approved server name:

```toml
[[mcp_servers]]
name = "test-validator"
```

The server will not start without explicit workspace permission. For a normal CLI run:

```text
cli-agent --with-os-read ...
```

For a flow step:

```toml
[[steps]]
id = "test"
workspace_access = "read"
```

`write` also satisfies the validator's minimum requirement, but the validator itself does not write to the real workspace. All test writes occur only inside the disposable container `/work`.

### Tool behavior

Python:

```text
run_python_tests(project_path=".")
run_python_tests(project_path=".", test_selector="tests/test_config.py::test_load")
```

The fixed command is equivalent to:

```text
python -m pytest -q [selector]
```

Java auto-detects Maven (`pom.xml`) or Gradle (`build.gradle` / `build.gradle.kts`):

```text
run_java_tests(project_path=".")
run_java_tests(project_path=".", test_selector="com.example.ExampleTest#works")
run_java_tests(project_path=".", build_system="gradle")
```

The fixed commands are:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 [-Dtest=<selector>] test
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test [--tests <selector>]
```

If both Maven and Gradle descriptors exist, set `build_system` explicitly.

See [docs/test-validator.md](docs/test-validator.md) for the full security and configuration details.

## Docker Compose MCP

See [docs/compose.md](docs/compose.md).

## Legacy Python Validator MCP

The existing Python build/start validator remains available for compatibility:

```text
cli-agent-python-validator-mcp
```

See [docs/python-validator.md](docs/python-validator.md). New test automation should generally use the Sandbox Test Validator above.
