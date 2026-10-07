# Sandbox Test Validator MCP

The Sandbox Test Validator runs Python and Java test suites in a short-lived Docker container while keeping the real `cli-agent` workspace outside that container.

## Tools

### Validation workflow

For ordinary Java programming changes, `run_java_build` is the primary validation step and should be attempted first. If it succeeds, the code change is considered validated for the programming task. `run_java_tests` must not be used merely as an additional generic validation step after a successful build.

The test tools are intended only for tasks that concern test cases themselves, for example creating, changing, debugging or explicitly verifying tests. The same principle applies to `run_python_tests`; this MCP intentionally has no generic Python build validator.

The MCP exposes exactly:

- `run_python_tests(project_path=".", test_selector=None)`
- `run_java_tests(project_path=".", test_selector=None, build_system="auto")`
- `run_java_build(project_path=".", build_system="auto")`

There is no arbitrary command, shell, Docker or package-install tool in the MCP contract. The Java build tool also does not accept arbitrary Maven goals, Gradle tasks or additional command-line arguments.

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
- omits common generated/cache directories. Build-output names such as `target`, `build`, `dist` and `.gradle` are excluded only at the selected project root or when their parent is recognizable as the corresponding Maven/Gradle/Python project, so legitimate nested source directories with those names remain in the snapshot,
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
- `/tmp`, `/work` and `/output` as tmpfs.

Project data is then streamed as an in-memory TAR archive through `docker exec -i ... tar -xf -` into `/work`; the real workspace is never mounted. The configured transfer timeout covers the streaming phase itself as well as the receiving process, while stdout/stderr are drained concurrently, so a blocked extraction cannot wait indefinitely before timeout handling begins.

The Docker socket is never mounted into the test container.

The container is removed after the test run.

Docker is a strong practical isolation layer but not a virtual-machine security boundary. Native Linux containers still share the host kernel.

## Images and dependencies

All images must be digest-pinned and already present locally. `--pull never` is mandatory. The images must also provide a POSIX `sh`, `tar`, `cat`, `cp` and `mkdir`, which the fixed sandbox runner uses for lifecycle, snapshot extraction, bounded output capture and offline-cache preparation.

### Python

The configured Python image must contain Python, pip and pytest. Project dependencies are provided by a separate prepared wheel cache.

A Windows pipx installation exposes `cli-agent-test-cache.exe` for Windows-side commands, but it is not sufficient for Python preparation. Install `cli-agent-mcp` through pipx inside WSL as well and invoke the Linux `cli-agent-test-cache` there. Calling the Windows `.exe` from a WSL shell still runs Windows Python and is rejected.

Python cache preparation **must run inside WSL**. Cache placement depends on where the MCP itself runs.

For a cli-agent/MCP installation running natively inside WSL, use the default native target:

```bash
cd /path/to/my-project
cli-agent-test-cache prepare-python .
```

For a Windows-hosted cli-agent/MCP where only preparation runs inside WSL, target the Windows user's cache:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-python . --target windows
```

The command checks that it is actually running under WSL and refuses preparation on native Windows. This avoids accidentally generating Windows-only wheels for the Linux Docker sandbox. The command also prints:

```text
Python dependency preparation: WSL is required.
Prepared under WSL: yes
```

Preparation uses the current WSL Python and its normal pip configuration. Private indexes such as a company JFrog/PyPI repository can therefore remain configured in the user's WSL pip configuration; those credentials are not passed to the MCP or test container.

`--target native` is the default for every preparation command and writes below the current environment's `~/.cli-agent/dependency-cache/<type>`. Under WSL, `--target windows` resolves the Windows user profile and maps the cache to the corresponding Windows directory through the WSL mount:

```text
~/.cli-agent/dependency-cache/python/python-<sha256>/wheels
```

The same target option is available for Maven and Gradle. An explicit `--cache-root` remains available for custom layouts and overrides target-based default placement; it must not be combined with `--target windows`.

Python test validation requires a `requirements.txt` in the selected project root. The v1 dependency contract is deliberately narrow: the root file and any recursive `-r/--requirement` or `-c/--constraint` files must stay inside the selected project and may contain pinned index dependencies in the form `package==version`. Compact include forms such as `-rrequirements/base.txt` and `-cconstraints.txt` are supported.

The validator does not derive Python dependencies from `pyproject.toml`, `uv.lock`, `poetry.lock` or `Pipfile.lock`, and it rejects editable installs, local path dependencies, direct URLs, VCS references and other pip options in the requirements graph. This is intentional: pip remains responsible for dependency resolution while the validator keeps a small, auditable cache contract.

To create the required file from the currently activated project environment, first ensure that the runtime and test dependencies you want to validate are installed in that environment, then run:

```bash
python -m pip freeze --exclude-editable > requirements.txt
```

For example, in a project that installs its test dependencies through an extra, a typical workflow is:

```bash
python -m pip install -e ".[test]"
python -m pip freeze --exclude-editable > requirements.txt
```

The exact install command before `pip freeze` is project-specific. `--exclude-editable` prevents the current project itself from being written as an editable/local dependency. Commit or otherwise maintain `requirements.txt` as the explicit validator dependency input.

Preparation builds wheels using pip:

```text
python -m pip wheel --wheel-dir <cache>/wheels -r requirements.txt
```

Preparation invokes pip exactly once for the complete requirements graph rooted at `requirements.txt`. This lets one pip resolver produce a coherent wheel set instead of resolving multiple inputs independently. After preparation, the cache contains a generated install manifest naming the prepared wheel files. During sandbox execution, pip installs only those local wheel paths; if the manifest is empty, the install step is skipped.

This step may use network access and private package credentials because it is deliberately a user-run action outside the MCP sandbox. Source distributions may execute their normal Python build backend while wheels are being produced.

The validator itself remains offline. It streams only the prepared wheel directory into `/tmp/python-wheels` and installs into disposable tmpfs with:

```text
python -m pip install \
  --no-index \
  --find-links /tmp/python-wheels \
  --target /tmp/python-deps \
  ...
```

The test process uses `PYTHONPATH=/tmp/python-deps:/work:/work/src`. No pip index configuration or credentials are copied into the sandbox.

If the matching cache is missing, `run_python_tests` returns `reason = "dependencies_not_prepared"` and explicitly states that `cli-agent-test-cache prepare-python <project>` must be run under WSL.

### Maven

The Maven image must contain Maven. By default both the validator and the preparation CLI use:

```text
~/.cli-agent/dependency-cache/maven
```

No cache path therefore has to be added to the admin policy for each project or user. If an organization wants another location, it can configure one shared root once with `--maven-cache-root`; the user then passes the same root to `cli-agent-test-cache prepare-maven --cache-root ...`.

The cache root is never selected by the model. For each Maven project the validator calculates a deterministic key from:

- every relevant `pom.xml` below the selected project, excluding generated/cache directories,
- root `.mvn/maven.config`,
- root `.mvn/extensions.xml`,
- root `.mvn/jvm.config`,
- the cache schema version.

Ordinary source changes therefore keep the same dependency key. Dependency/build-configuration changes produce a new key.

Prepare the cache as the normal user. For the normal Windows-hosted MCP case:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project
```

If a project has OS-/architecture-dependent Maven profiles or dependencies and the Linux sandbox cannot use the Windows-prepared offline cache, retry preparation from WSL while targeting the Windows cache:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-maven . --target windows
```

For a fully WSL-hosted cli-agent/MCP installation, run the same command in WSL without `--target windows`.

The default preparation root is:

```text
~/.cli-agent/dependency-cache/maven
```

Use `--cache-root` if the administrator configured a different root:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project `
  --cache-root D:\cli-agent-dependency-cache\maven
```

Preparation intentionally runs outside the MCP sandbox. Maven may use the user's normal `settings.xml` for repository, mirror and credential configuration. If user settings define profiles/active profiles that alter the effective build model, preparation fails closed; move that build semantics into the project POM before using the offline validator. Project-specific alternate settings via `-s` / `--settings` in `.mvn/maven.config` are also rejected. It builds an isolated local repository using:

```text
mvn -B -Dmaven.repo.local=<cache>/repository dependency:go-offline
mvn -B -Dmaven.repo.local=<cache>/repository -DskipTests package
```

The preparation command stores only the generated Maven repository and a small readiness marker under `maven-<sha256>`; it does not copy `settings.xml` or JFrog credentials into the prepared cache.

During a test or build the validator computes the same key. If no matching ready cache exists, it returns:

```text
reason = "dependencies_not_prepared"
```

No network fallback occurs. When the cache exists, its repository tree is validated, streamed directly from the host through Docker stdin into `/tmp/m2`, and Maven runs:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 test
```

or, with a selector:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -Dtest=<selector> test
```

The host cache is never bind-mounted and is never writable by project code. Maven build-only validation uses the same cache and fixed command:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -DskipTests package
```

This intentionally skips test execution while still compiling/package-building the project. Test-time modifications happen only in container tmpfs and disappear with the container.

### Gradle

The Gradle image must contain Gradle. By default both validator and preparation CLI use:

```text
~/.cli-agent/dependency-cache/gradle
```

Prepare the cache as the normal user. For the normal Windows-hosted MCP case:

```powershell
cli-agent-test-cache prepare-gradle C:\dev\my-project
```

If platform-dependent Gradle build logic or dependencies make the Windows-prepared cache incomplete for the Linux sandbox, retry from WSL while targeting the Windows cache:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-gradle . --target windows
```

For a fully WSL-hosted cli-agent/MCP installation, omit `--target windows`.

The command derives a deterministic key from Gradle build/configuration files, including `build.gradle(.kts)`, `settings.gradle(.kts)`, Gradle properties, wrapper properties, all `*.versions.toml` version catalogs, verification metadata and the full source/configuration trees of literal local `includeBuild(...)` builds such as `build-logic`. Ordinary application source-only changes therefore keep the same key.

Preparation prefers the project's Gradle wrapper (`gradlew.bat` on Windows or `gradlew` otherwise) and falls back to Gradle from PATH. It uses a fresh isolated Gradle user home and executes `assemble` and `testClasses` plus an internal temporary init script that resolves all resolvable runtime classpaths named `runtimeClasspath`, `testRuntimeClasspath`, or ending in `RuntimeClasspath`. The same init script disables every Gradle task of type `Test`, so project task wiring cannot cause tests to run during preparation.

To support private repositories such as a company JFrog, the preparation command copies only the user's Gradle configuration files (`gradle.properties`, root init scripts and regular files in `init.d`) from the normal Gradle user home into that temporary isolated home. Before promotion, the preparer removes the copied user configuration and discards all generated Gradle user-home state except the downloaded module dependency cache at `caches/modules-2`. This also removes compiled init-script/DSL artifacts. Older pre-sanitization Gradle caches use a previous cache schema and are rejected.

This is an intentional security boundary: user-specific `init.gradle(.kts)` / `init.d` rules are not replayed inside the sandbox. Therefore an offline build must not require those user-home init scripts for its build semantics after dependencies are already cached. If an organization needs mandatory repository/plugin-resolution logic during offline replay, that logic must be supplied separately in a credential-free, administrator-controlled form or moved into project configuration.

If no matching ready cache exists, `run_java_tests(..., build_system="gradle")` returns `reason = "dependencies_not_prepared"`. There is no network fallback.

When a cache exists, its prepared Gradle user home is validated and streamed into disposable container tmpfs at `/tmp/gradle`. The validator test tool then runs:

```text
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test
```

or:

```text
gradle --offline --no-daemon --gradle-user-home /tmp/gradle test --tests <selector>
```

The separate Gradle build tool uses the same prepared cache but runs only:

```text
gradle --offline --no-daemon --gradle-user-home /tmp/gradle --init-script /tmp/cli-agent-disable-tests.gradle assemble
```

Before the build, the validator writes a fixed temporary init script that disables all Gradle tasks of type `org.gradle.api.tasks.testing.Test`; the build then invokes `assemble` with that init script. This prevents standard/custom Gradle Test tasks from being scheduled even if `assemble` depends on them. Arbitrary custom non-Test tasks remain part of project build semantics. The host cache is never bind-mounted or writable by project code. If an organization uses a non-default cache root, configure `--gradle-cache-root` once and pass the same root to `prepare-gradle --cache-root ...`.

## Output and secret handling

Container stdout/stderr is redirected to the bounded `/output` tmpfs before it can reach the host process, then truncated/redacted before being returned to the model.

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
--maven-cache-root D:/optional/shared/cli-agent-maven-cache
--gradle-cache-root D:/optional/shared/cli-agent-gradle-cache
--python-cache-root D:/optional/shared/cli-agent-python-cache
```

These are launch-time administrator settings, not MCP tool arguments, so the model cannot relax them.


## Unified Java build tool

`run_java_build(project_path=".", build_system="auto")` uses exactly the same Maven/Gradle auto-detection as `run_java_tests`. A project containing both Maven and Gradle descriptors is considered ambiguous and requires an explicit `build_system`.

The model sees only this unified build tool. Internally it dispatches to the fixed Maven or Gradle build implementation:

```text
Maven  -> mvn -o -B -Dmaven.repo.local=/tmp/m2 -DskipTests package
Gradle -> gradle --offline --no-daemon --gradle-user-home /tmp/gradle assemble
```

The separate Maven/Gradle build helpers are implementation details and are not exposed as MCP tools.
