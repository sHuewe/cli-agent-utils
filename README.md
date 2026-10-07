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

The test validator is the recommended validator for automated code checks. It exposes three model-visible tools:

```text
run_python_tests
run_java_tests
run_java_build
```

It does **not** expose an arbitrary shell, generic Docker command, arbitrary Maven goal, or arbitrary Gradle task.

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
- removes the short-lived container after the run,
- enforces transfer timeouts while project/dependency TAR streams are still being written, so a blocked extraction cannot bypass the configured timeout.

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

For Python, dependency preparation follows the same model but **must be executed inside WSL**. This is intentional: the Docker validator runs Linux containers, so preparing with Windows pip could create Windows-only wheels.

Cache placement is explicit and consistent across Maven, Gradle and Python. `--target native` is the default and writes to the current environment's `~/.cli-agent/dependency-cache/<type>`. Use this when cli-agent and the MCP run in the same environment as preparation. For example, a fully WSL-hosted setup uses:

```bash
cli-agent-test-cache prepare-python .
```

If cli-agent/MCP run on Windows but preparation is deliberately executed inside WSL, target the Windows user's cache instead:

```bash
cli-agent-test-cache prepare-python . --target windows
```

Under WSL, `--target windows` resolves the Windows user profile and writes to the corresponding Windows `~/.cli-agent/dependency-cache/python` directory through the WSL mount. The command still uses the WSL user's normal pip configuration, including configured private PyPI/JFrog indexes and credentials. The validator itself never receives pip/JFrog credentials. Preparation also writes a cache-local wheel manifest. The sandbox installs only those prepared wheel files and never replays original direct URL, VCS, or local-project requirement references.

During tests the wheel cache is streamed into the sandbox and dependencies are installed only with:

```text
python -m pip install --no-index --find-links /tmp/python-wheels --target /tmp/python-deps ...
```

If the Python dependency files change and the matching cache is missing, the MCP returns `dependencies_not_prepared` and explicitly tells the user to run `prepare-python` under WSL.

For Maven, the validator and preparation CLI use the same per-user cache root by default: `~/.cli-agent/dependency-cache/maven`. The admin policy therefore does **not** need a project-specific or user-specific cache path. An administrator can override the root once with `--maven-cache-root` if required. Each project dependency state gets a deterministic key derived from all relevant `pom.xml` files and root `.mvn` configuration. The user normally prepares that key in the same host environment as the MCP with the normal Maven/JFrog setup:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project
```

The command uses the user's normal Maven configuration and credentials, but writes dependencies into a separate repository below:

```text
%USERPROFILE%\.cli-agent\dependency-cache\maven\maven-<sha256>\repository
```

The test validator never receives Maven/JFrog credentials. It calculates the same key, streams only that prepared repository into container tmpfs, and executes Maven offline. Cache preparation now runs through the Maven `package` lifecycle with `-DskipTests`, so build/package plugins needed by `run_maven_build` are prepared as well. Source changes do not invalidate the cache; relevant POM/configuration changes produce a new key and require preparation again.

For Gradle, the validator and preparation CLI use `~/.cli-agent/dependency-cache/gradle` by default. Prepare the current build configuration once as the normal user in the same host environment as the MCP:

```powershell
cli-agent-test-cache prepare-gradle C:\dev\my-project
```

Preparation runs Gradle outside the MCP sandbox with the user's normal repository setup and prepares `assemble`, `testClasses`, and resolvable runtime classpaths (including `runtimeClasspath`, `testRuntimeClasspath`, and similarly named custom runtime classpaths). During preparation, all Gradle `Test` tasks are disabled by the validator-controlled init script so project wiring such as `assemble.dependsOn(test)` cannot execute tests. A project Gradle wrapper is preferred when present; otherwise Gradle from PATH is used. A temporary isolated Gradle user home is used; `gradle.properties` and init scripts from the user's normal Gradle home are copied only for preparation. Before promotion, all user configuration and compiled/script/DSL cache state is discarded and only Gradle's downloaded module dependency cache (`caches/modules-2`) is retained. Consequently, the offline sandboxed build must not depend on user-specific init scripts for build semantics. If an organization requires such rules during offline execution, provide them as project configuration or via a separately administered credential-free sandbox configuration rather than relying on the user's Gradle home. The resulting Gradle user home is streamed into `/tmp/gradle` and tests run with `--offline`.

Relevant Gradle build/configuration changes, including custom `*.versions.toml` catalogs and literal local `includeBuild(...)` build-logic sources, generate a new dependency key. Ordinary application source-only changes keep the existing cache.

Maven and Gradle preparation normally works directly on Windows for typical platform-independent Java builds. Some projects intentionally resolve different dependencies or activate different build logic depending on operating system or architecture. If a Windows-prepared cache fails later in the Linux sandbox for that reason, retry preparation inside WSL while still targeting the Windows-hosted MCP cache:

```bash
cli-agent-test-cache prepare-maven . --target windows
cli-agent-test-cache prepare-gradle . --target windows
```

For a cli-agent/MCP installation that itself runs inside WSL, omit `--target windows`; the default `--target native` correctly uses the WSL user's own cache.

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

For Java programming tasks, `run_java_build` is the primary validation tool after code changes. The agent should call it first. If it succeeds, the implementation is considered validated for a normal coding task and `run_java_tests` should not be run merely as an extra validation step. Test tools are reserved for work that actually concerns test cases, such as creating, modifying, debugging or explicitly verifying tests.

Python:

```text
run_python_tests(project_path=".")
run_python_tests(project_path=".", test_selector="tests/test_config.py::test_load")
```

The fixed test command is equivalent to:

```text
python -m pytest -q [selector]
```

When Python dependencies are declared in common `requirements*.txt`, `pyproject.toml` project dependencies, or test/dev dependency groups, a matching WSL-prepared wheel cache is required first. Recursive requirements includes are resolved relative to the including file, and PEP 735 `include-group` entries are expanded recursively. Lockfile-based resolution (`uv.lock`, `poetry.lock`, `Pipfile.lock`) is rejected explicitly; export pinned dependencies to a supported requirements file instead. Relative PEP 508 dependencies from `pyproject.toml` are allowed when they stay inside the selected project and their complete input tree is included in the cache key. References outside the selected project remain rejected. Empty/comment-only requirements files are valid and produce an empty wheel manifest.

For Java code changes, prefer `run_java_build`. Java test execution is intended only when the task concerns test cases. Java auto-detects Maven (`pom.xml`) or Gradle (`build.gradle` / `build.gradle.kts`):

```text
run_java_tests(project_path=".")
run_java_tests(project_path=".", test_selector="com.example.ExampleTest#works")
run_java_tests(project_path=".", build_system="gradle")
```

The fixed test commands are:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 [-Dtest=<selector>] test
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test [--tests <selector>]
```

Java also has one unified build-only tool:

```text
run_java_build(project_path=".")
run_java_build(project_path=".", build_system="maven")
run_java_build(project_path=".", build_system="gradle")
```

It uses the same auto-detection rules as `run_java_tests`. The underlying commands are fixed to:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -DskipTests package
gradle --offline --no-daemon --gradle-user-home /tmp/gradle --init-script /tmp/cli-agent-disable-tests.gradle assemble
```

There is deliberately no Python build tool.

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
