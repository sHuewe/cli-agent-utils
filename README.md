# cli-agent-mcp

Optional MCP servers for [`cli-agent`](https://github.com/sHuewe/cli-agent).

This repository contains MCP servers whose capabilities require Docker or other host-side execution surfaces that are intentionally kept outside the `cli-agent` core.

Currently included:

- **Docker Compose MCP**: inspect and optionally control a Compose project.
- **Python Validator MCP**: legacy build/start validation for Python projects.
- **Sandbox Test Validator MCP**: run Python/pytest and Java/Maven/Gradle tests in a hardened short-lived Docker sandbox.

## Installation

On Windows, a normal pipx installation exposes the console scripts globally through the pipx app directory:

```powershell
py -m pipx install .
Get-Command cli-agent-test-validator-mcp
Get-Command cli-agent-test-cache
```

This Windows installation is sufficient for the MCP server, `prepare-maven` and `prepare-gradle`.

`prepare-python` is different: it deliberately requires a real Linux Python process under WSL so that Linux-compatible wheels are built for the Docker sandbox. Therefore install this package a second time inside WSL:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install .
```

When installing from Git rather than a checkout, use the same repository/ref in Windows and WSL. Running the Windows `cli-agent-test-cache.exe` from a WSL shell does not count as WSL preparation; `prepare-python` verifies that its Python interpreter itself runs under WSL.

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
cli-agent-test-cache
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

- a Python image containing Python, `pip` and `pytest`; project dependencies are supplied from a separately prepared Linux wheel cache,
- a Maven image containing Maven; project dependencies can be supplied from a separately prepared per-dependency cache,
- a Gradle image containing Gradle; project dependencies can be supplied from a separately prepared per-dependency Gradle user home.

Every reference must include a complete SHA-256 digest:

```text
registry.internal/python-tests@sha256:<64-hex-digest>
registry.internal/maven-tests@sha256:<64-hex-digest>
registry.internal/gradle-tests@sha256:<64-hex-digest>
```

The validator never downloads packages during a test. Python installs only from a prepared local wheel cache with `--no-index`; Maven runs with `-o`; Gradle runs with `--offline`.

For Python, dependency preparation follows the same model but **must be executed inside WSL**. This is intentional: the Docker validator runs Linux containers, so preparing with Windows pip could create Windows-only wheels. Run from the project inside WSL:

```bash
cli-agent-test-cache prepare-python .
```

The command prints that WSL is required and records that the cache was prepared under WSL. It uses the WSL user's normal pip configuration, including configured private PyPI/JFrog indexes and credentials, and builds a separate wheel cache. By default the cache is written to the Windows user's corresponding `~/.cli-agent/dependency-cache/python` directory so that the Windows-hosted MCP sees the same files. The validator itself never receives pip/JFrog credentials.

During tests the wheel cache is streamed into the sandbox and dependencies are installed only with:

```text
python -m pip install --no-index --find-links /tmp/python-wheels --target /tmp/python-deps ...
```

If the Python dependency files change and the matching cache is missing, the MCP returns `dependencies_not_prepared` and explicitly tells the user to run `prepare-python` under WSL.

For Maven, the validator and preparation CLI use the same per-user cache root by default: `~/.cli-agent/dependency-cache/maven`. The admin policy therefore does **not** need a project-specific or user-specific cache path. An administrator can override the root once with `--maven-cache-root` if required. Each project dependency state gets a deterministic key derived from all relevant `pom.xml` files and root `.mvn` configuration. The user prepares that key outside the agent with the normal Maven/JFrog setup:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project
```

The command uses the user's normal Maven configuration and credentials, but writes dependencies into a separate repository below:

```text
%USERPROFILE%\.cli-agent\dependency-cache\maven\maven-<sha256>\repository
```

The test validator never receives Maven/JFrog credentials. It calculates the same key, streams only that prepared repository into container tmpfs, and executes Maven offline. Source changes do not invalidate the cache; relevant POM/configuration changes produce a new key and require preparation again.

For Gradle, the validator and preparation CLI use `~/.cli-agent/dependency-cache/gradle` by default. Prepare the current build configuration once as the normal user:

```powershell
cli-agent-test-cache prepare-gradle C:\dev\my-project
```

Preparation runs Gradle outside the MCP sandbox with the user's normal repository setup. A temporary isolated Gradle user home is used; `gradle.properties` and init scripts from the user's normal Gradle home are copied only for preparation and removed before the cache is marked ready. This allows private repository/JFrog credentials to be used during preparation without exposing those configuration files to the validator. The resulting Gradle user home is streamed into `/tmp/gradle` and tests run with `--offline`.

Relevant Gradle build/configuration changes generate a new dependency key. Source-only changes keep the existing cache.

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

The fixed test command is equivalent to:

```text
python -m pytest -q [selector]
```

When Python dependencies are declared in common `requirements*.txt`, `pyproject.toml` project dependencies, or test/dev dependency groups, a matching WSL-prepared wheel cache is required first.

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

If the Maven or Gradle cache for the current dependency key is missing, the tool returns `reason = "dependencies_not_prepared"` and the required key. Run `cli-agent-test-cache prepare-maven <project>` or `prepare-gradle <project>` as the user, then retry. The machine-wide admin policy does not need to change per project.

See [docs/test-validator.md](docs/test-validator.md) for the full security and configuration details.

## Docker Compose MCP

See [docs/compose.md](docs/compose.md).

## Legacy Python Validator MCP

The existing Python build/start validator remains available for compatibility:

```text
cli-agent-python-validator-mcp
```

See [docs/python-validator.md](docs/python-validator.md). New test automation should generally use the Sandbox Test Validator above.
