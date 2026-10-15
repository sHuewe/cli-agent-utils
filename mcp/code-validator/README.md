# Code-Validator MCP

Install just this distribution:

```bash
pipx install ./mcp/code-validator
```

This installs the `cli-agent-code-validator-mcp` MCP command and `cli-agent-dependency-cache` preparation CLI, not Compose or the removed legacy validator. For development, install `./mcp/code-validator[dev]`.

The former `validate_python_project` application-start tool has been removed and is **not** replaced by the current Python test runner.

## Code-Validator MCP

The code validator is the recommended validator for automated code checks. It exposes three model-visible tools:

```text
run_python_tests
run_java_tests
run_java_build
```

It does **not** expose an arbitrary shell, generic Docker command, arbitrary Maven goal, or arbitrary Gradle task.

### MCP result channels

The model-visible part of every tool result is returned through normal MCP `content` and, when supported by the installed MCP SDK, `structuredContent`. An optional direct user notice is carried separately in:

```text
_meta["io.github.shuewe.cli-agent/messageToUser"].text
```

The Code-Validator uses this channel for information that is intended for the human operator rather than the model. In particular, dependency-cache remediation commands are placed only in this metadata. The model-visible result receives a non-actionable explanation such as `dependencies_not_prepared` or `dependency_cache_may_be_stale`, so an LLM is not instructed to execute the trusted host-side preparation command itself.

The metadata field is optional and may also be present on successful tool calls. MCP metadata is an application/client channel, not a cryptographic confidentiality boundary; the intended separation becomes an enforced boundary only when the MCP host deliberately keeps this namespaced metadata out of the model context. Clients that do not implement this extension may ignore it.

### Security model

The validator requires at least `workspace_access = "read"` from `cli-agent`. Its threat model covers untrusted project contents and model-triggered execution, not a separate malicious host process that already has permission to race and mutate the workspace concurrently. The workspace path and effective permission are supplied by the Core through the reserved environment variables:

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

Project files such as `.env` are intentionally part of the project snapshot when they are present in the selected project because many real test suites require their normal configuration files. Test code can therefore read them inside the no-network sandbox. Before output is returned to the model, JSON, TOML, YAML, `.env` and Java `.properties` files are parsed with format-aware parsers and values below sensitive keys are collected for exact redaction; common credential-output patterns are redacted as a second layer. Java properties retain their byte-level ISO-8859-1 semantics during parsing, dotted sensitive keys such as `service.api.key` are recognized, and malformed sensitive `.env` bindings cause fail-closed output suppression. If a candidate config cannot be parsed while still containing a possible sensitive-key marker, or if fixed discovery bounds are exceeded, the validator suppresses captured stdout/stderr rather than returning potentially unredacted logs. Redaction remains defense in depth rather than a complete confidentiality boundary against deliberately transformed output.

### Required Docker images

Three immutable image references are configured administratively. Each image must provide a POSIX `sh`, `tar`, `cat`, `cp`, `mkdir` and `sleep` in addition to the language/build tooling:

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

For concrete image recommendations, Java/JDK compatibility examples, local digest-pinning guidance, and the repository's configurable Gradle image Dockerfile, see [Validator Docker images](docs/images.md). The official Gradle image is intentionally treated only as a build source there because its declared Gradle-home volume conflicts with the validator's no-image-volumes policy.

### Optional Docker dependency preparation for Java

The explicitly invoked `cli-agent-dependency-cache` CLI supports an optional
Docker executor for Maven and Gradle, in addition to the existing Python wheel
executor. This is a **trusted, network-enabled prepare operation**, never an
MCP tool or a way for the LLM to start arbitrary builds. Host preparation
remains the default.

```powershell
cli-agent-dependency-cache prepare-maven . --executor docker --image company/maven:3.9 --cache-root C:\mc --wsl
cli-agent-dependency-cache prepare-gradle . --executor docker --image company/gradle:8 --wsl
```

By default, Docker prepare streams Maven, Gradle, and Python/pip build output
live to the invoking operator terminal. `--verbose` makes this explicit;
`--quiet` suppresses build output. Transfer/setup stages print progress
messages in the default mode. This output is **not** returned by MCP tools,
recorded as a persistent log by the preparer, or passed to an LLM. However,
build tools may print repository credentials or secrets themselves; use a
trusted terminal and avoid redirecting verbose output into shared logs.
The existing execution timeout remains enforced.

Docker images must already be present locally, may use tags, and are the
operator's responsibility: matching Java/build tool versions, company CAs,
network/proxy settings and other build dependencies. Docker uses bridge
networking. The *whole selected project tree*, including `.git` when present,
is safely TAR-streamed into a temporary container without host bind mounts.
Symlinks, reparse points and special filesystem objects are rejected; projects
with such entries must be adjusted before preparation. Build scripts run with
network access and can execute arbitrary code. The temporary project snapshot
is not published back to the host.

User settings are transferred selectively by default: Maven
`~/.m2/settings.xml` and `settings-security.xml`; Gradle's
`gradle.properties`, init scripts and `init.d` files from the selected
Gradle user home. Use `--no-user-config` to disable the transfer.
The image's system-wide configuration and required certificates are not
automatically imported from the host.

Only Maven's prepared `repository` or Gradle's
`gradle-home/caches/modules-2` is exported, through size-bounded TAR transfer
with path traversal, symlinks, special entries and Windows drive paths rejected.
Maven provenance files (`_remote.repositories`, `resolver-status.properties`,
`*.lastUpdated`) are stripped. Gradle prepared script and user configuration
caches are discarded. Existing successful cache snapshots are retained if
preparation or export fails. The normal MCP validator still uses its distinct
digest-pinned images, `--network none`, and sees no transferred credentials.

Do not use Docker-prepare for untrusted project build scripts or untrusted
images. A malicious build can access credentials during preparation, and
arbitrary plugins can potentially write secrets into generated artifacts.
The cache allowlists and metadata checks reduce, but cannot completely
eliminate, that risk.

### Optional Python Docker wheel preparation

In addition to Maven and Gradle, `prepare-python` supports Docker execution.
Unlike the Java preparation commands above, Python Docker preparation copies
only its selected requirements and constraints files:

```bash
cli-agent-dependency-cache prepare-python . --executor docker --image python:3.12
```

Host mode is the default and still requires WSL Python. Docker mode accepts an
image tag or digest (unlike the administrator-pinned validator images), requires
the selected image to exist locally (`--pull never`), and always uses Docker
bridge networking. No user-home or project bind mounts are made. The temporary
container receives **only the root `requirements.txt` and all recursively
referenced `-r` requirements / `-c` constraints files**. Local package paths
are not supported in Docker mode; use host mode for these.

A single selected pip user configuration file is transferred when available;
`--no-user-config` disables that. Explicit `PIP_CONFIG_FILE=/dev/null` is
honored. The temporary container needs `sh`, `tar`, `mkdir`, `sleep`,
Python and pip. Only generated wheel files are exported to the host and used by
the unchanged, offline, digest-pinned MCP validator.

Docker prepare is a *trusted, manually invoked CLI operation*, never an MCP
tool or an LLM-exposed action. pip build backends may run project-controlled
code and read credentials supplied to this network-enabled preparation
container. Run it only for trusted dependencies and images. Python/ABI
compatibility with the separately administered validator image remains the
operator's responsibility.

All `prepare-*` commands are explicit, trusted operator actions outside the agent sandbox. They may evaluate project-controlled build logic with the current user's permissions, network access and configured package credentials. Their job is only to create a credential-free offline artifact snapshot for later use by the sandbox. A prepared cache is **not** a proof that it contains the dependencies required by the project at validation time, and the validator deliberately does not try to prove semantic equivalence between preparation and the later offline build. Profiles, dynamic versions, snapshots, platform-dependent logic or ordinary project changes can therefore make an existing cache incomplete. The sandbox simply tries the current project against the existing cache and fails closed; recognized missing-dependency failures ask the user to rerun the matching `prepare-*` command.

For Python, **host preparation must be executed inside WSL**, because Windows pip can create Windows-only wheels. The interpreter selected by `--python-command` must report Linux. Alternatively, **Docker preparation** (`prepare-python --executor docker --image <image>`) creates Linux wheels in a temporary container and does not require WSL Python.

**Operational compatibility requirement:** wheel preparation uses the selected WSL Python interpreter (host mode) or the explicitly selected Docker image (Docker mode), while test execution uses the administrator-configured Docker image. The validator deliberately does not try to infer or enforce wheel-tag/ABI compatibility between those environments. The administrator is responsible for keeping Python implementation/version, architecture and relevant platform ABI compatible between preparation and the pinned test image. A mismatch can cause the offline install to fail even though a cache exists; it is not treated as a sandbox escape or credential boundary issue.

Cache placement is explicit and consistent across Maven, Gradle and Python. `--target native` is the default and writes to the current environment's `~/.cli-agent/dependency-cache/<type>`. Use this when cli-agent and the MCP run in the same environment as preparation. For example, a fully WSL-hosted setup uses:

```bash
cli-agent-dependency-cache prepare-python .
```

If cli-agent/MCP run on Windows but preparation is deliberately executed inside WSL, target the Windows user's cache instead:

```bash
cli-agent-dependency-cache prepare-python . --target windows
```

Under WSL, `--target windows` resolves the Windows user profile and writes to the corresponding Windows `~/.cli-agent/dependency-cache/python` directory through the WSL mount. If the Windows-hosted validator uses a non-default Windows cache root, preparation from WSL must pass both `--target windows` (for the Windows project identity) and `--cache-root <wsl-mounted-path>` (for the administrator-configured cache location). The command still uses the WSL user's normal pip configuration, including configured private PyPI/JFrog indexes and credentials. The validator itself never receives pip/JFrog credentials. Preparation also writes a cache-local wheel manifest. The sandbox installs only those prepared wheel files. The requirements contract permits pinned index dependencies and non-editable local package paths (including paths outside the project and local `file://` direct references). Trusted host preparation resolves these locations into wheels. Remote URLs, VCS and editable dependencies remain rejected; the offline validator receives only the prepared wheels, never the local source directories.

During tests the wheel cache is streamed into the sandbox and dependencies are installed only with:

```text
python -m pip install --no-index --find-links /tmp/python-wheels --target /tmp/python-deps ...
```

The Python cache is project-scoped rather than dependency-content-scoped. The validator reuses the most recently prepared cache for that project until an offline install/test indicates that the cache may be stale. Running `prepare-python` always rebuilds and replaces only after a successful preparation that project's cache.

For Maven, the validator and preparation CLI use the same per-user cache root by default: `~/.cli-agent/dependency-cache/maven`. The admin policy therefore does **not** need a project-specific or user-specific cache path. Each project gets one stable cache identity derived from the cache type plus the normalized absolute project root path; Maven/POM contents are deliberately not interpreted to decide cache freshness. The user prepares or refreshes that project cache in the same host environment as the MCP with the normal Maven/JFrog setup:

```powershell
cli-agent-dependency-cache prepare-maven C:\dev\my-project
```

The command uses Maven's normal user/global configuration and credentials, including the user's standard `~/.m2/settings.xml`, the selected Maven installation's global `conf/settings.xml`, profiles, mirrors and repository configuration. Those inputs belong to the trusted preparation environment and are deliberately **not** replayed or interpreted by the sandbox validator. Dependencies are written into a separate repository below:

```text
%USERPROFILE%\.cli-agent\dependency-cache\maven\maven-<sha256>\repository
```

Preparation may also be affected by project Maven configuration such as `.mvn/maven.config`. That is acceptable: preparation is not the sandbox boundary, and no guarantee is made that its effective build model matches the later fixed offline invocation.

Before promotion, Maven resolver-only provenance/state files such as `_remote.repositories`, `resolver-status.properties` and `*.lastUpdated` are removed from the prepared repository. This is intentional: the sandbox does not receive the user's mirror/repository settings, and the prepared cache is treated as an explicit offline artifact snapshot rather than as a normal Maven download cache. Artifacts therefore remain usable even when preparation used a company mirror such as JFrog. The code validator never receives Maven/JFrog credentials. It calculates the same project identity, streams only that prepared repository into container tmpfs, and executes Maven offline. Cache preparation first runs the Maven `package` lifecycle with `-DskipTests`, then runs a test warm-up (`mvn -Dmaven.test.failure.ignore=true test`) using the same isolated repository. Test assertion failures are nonfatal to cache promotion. The warm-up triggers dynamically selected test-plugin dependencies (such as Surefire JUnit Platform providers) without hardcoding provider artifacts; tests may execute with side effects and may contact external systems. Use `--skip-test-warmup` to disable it. Timeouts and preparation infrastructure errors remain fatal. Changes to POMs, parent POMs, modules or other Maven inputs do **not** create a new cache key. If the offline build reports unresolved/missing dependencies, the tool returns a user-facing hint to run `prepare-maven` again. Every preparation builds a fresh temporary cache and replaces only after a successful preparation the previous cache for that project.

For Gradle, the validator and preparation CLI use `~/.cli-agent/dependency-cache/gradle` by default. Prepare the current build configuration once as the normal user in the same host environment as the MCP:

```powershell
cli-agent-dependency-cache prepare-gradle C:\dev\my-project
```

Preparation runs Gradle outside the MCP sandbox with the user's normal repository setup and prepares `assemble`, `testClasses`, and resolvable runtime classpaths (including `runtimeClasspath`, `testRuntimeClasspath`, and similarly named custom runtime classpaths). Gradle preparation is an explicit trusted host action: evaluating the project build can execute arbitrary Gradle project/plugin logic with the current user's permissions, network access and repository credentials. The helper init script only resolves runtime classpaths; it does not claim to suppress project-defined test or other task execution. A project Gradle wrapper is preferred during preparation when present; otherwise Gradle from PATH is used. Sandbox validation always uses the Gradle executable from the administrator-pinned image, so keeping that Gradle version compatible with the project's wrapper version is an administrator responsibility. A temporary isolated Gradle user home is used; `gradle.properties` and init scripts from the user's normal Gradle home are copied only for preparation. Before promotion, all user configuration and compiled/script/DSL cache state is discarded and only Gradle's downloaded module dependency cache (`caches/modules-2`) is retained. Gradle repository metadata inside that cache is checked as well: promotion is rejected if a `resource-at-url.bin` contains URL userinfo such as `https://user:token@host/`, because that would otherwise move repository credentials into the sandbox. Consequently, the offline sandboxed build must not depend on user-specific init scripts for build semantics. If an organization requires such rules during offline execution, provide them as project configuration or via a separately administered credential-free sandbox configuration rather than relying on the user's Gradle home. The resulting Gradle user home is streamed into `/tmp/gradle` and tests run with `--offline`.

Gradle cache freshness is deliberately **not** inferred from build scripts. The cache identity depends only on the normalized project root path, so arbitrary Gradle build logic such as `buildSrc`, `includeBuild(...)`, custom property files or dynamically computed dependency coordinates does not need to be parsed by cli-agent. If an offline Gradle build cannot resolve a dependency, the result includes a user-facing hint to rerun `prepare-gradle`; preparation always replaces that project's previous cache only after a successful preparation.

Maven and Gradle preparation normally works directly on Windows for typical platform-independent Java builds. Some projects intentionally resolve different dependencies or activate different build logic depending on operating system or architecture. If a Windows-prepared cache fails later in the Linux sandbox for that reason, rerun preparation inside WSL while targeting the Windows-hosted MCP cache. Preparation always replaces the existing project cache:

```bash
cli-agent-dependency-cache prepare-maven . --target windows
cli-agent-dependency-cache prepare-gradle . --target windows
```

For a cli-agent/MCP installation that itself runs inside WSL, omit `--target windows`; the default `--target native` correctly uses the WSL user's own cache.

The images must already exist in the Docker daemon because the validator uses `--pull never`. The pinned images must provide a POSIX `sh` plus `tar`, `cat`, `cp`, `mkdir`, and `sleep`; `sleep` is used by the fixed container keepalive entrypoint while validation commands run via `docker exec`.

### cli-agent admin configuration

With current `cli-agent`, external stdio launch configuration belongs in the machine-wide `admin_config.toml`. First determine the absolute executable path, for example on Windows:

```powershell
(Get-Command cli-agent-code-validator-mcp).Source
```

Then configure the trusted server:

```toml
[[mcp.trusted_servers]]
name = "code-validator"
transport = "stdio"
command = "C:/absolute/path/to/cli-agent-code-validator-mcp.exe"
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
name = "code-validator"
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

Python test validation requires a root `requirements.txt`. The supported contract permits pinned index dependencies (`package==version`), explicit local non-editable Python package paths (`../my-library`, `./vendor/library`), local `file://` direct references (`my-library @ file:///path/to/my-library`), and recursive `-r/--requirement` and `-c/--constraint` files inside the selected project. Local source paths may be outside the project and are resolved only by trusted host preparation, not by the offline validator. Remote URLs, VCS and editable installations remain disallowed. Poetry/uv/Pipenv lockfiles are not read. The project still requires a root `requirements.txt`. Export the exact test environment to `requirements.txt` first. In an activated project virtual environment, the standard pip command is:

```bash
python -m pip freeze --exclude-editable > requirements.txt
```

Install the project's runtime/test dependencies into that environment before freezing it. The validator then resolves the entire dependency set in one pip invocation and prepares an offline wheel cache.

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

Native test-runner semantics apply consistently to Python, Maven, and Gradle: a successful tool result means the fixed pytest/Maven/Gradle command exited successfully according to the project's own configuration. The validator does not separately require tests to exist, require a selector to match, or override project settings that intentionally ignore test failures.

Java also has one unified build-only tool:

```text
run_java_build(project_path=".")
run_java_build(project_path=".", build_system="maven")
run_java_build(project_path=".", build_system="gradle")
```

It uses the same auto-detection rules as `run_java_tests`. The underlying commands are fixed to:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -DskipTests package
gradle --offline --no-daemon --gradle-user-home /tmp/gradle assemble
```

There is deliberately no Python build tool.

If both Maven and Gradle descriptors exist, set `build_system` explicitly.

If a project cache has never been prepared, the tool returns `reason = "dependencies_not_prepared"` plus a user-facing preparation command. If a cached offline build fails with a recognized missing-dependency pattern, it returns `reason = "dependency_cache_may_be_stale"` and asks the user to rerun the matching `prepare-*` command. Cache freshness is therefore determined by the build/install attempt, not by cli-agent parsing dependency files.

See [security documentation](docs/security.md) for the full security and configuration details.

