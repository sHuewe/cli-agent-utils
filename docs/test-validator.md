# Sandbox Test Validator MCP

The Sandbox Test Validator runs Python and Java test suites in a short-lived Docker container while keeping the real `cli-agent` workspace outside that container.

## Tools

### Validation workflow

For ordinary Java programming changes, `run_java_build` is the primary validation step and should be attempted first. If it succeeds, the code change is considered validated for the programming task. `run_java_tests` must not be used merely as an additional generic validation step after a successful build.

The test tools are intended only for tasks that concern test cases themselves, for example creating, changing, debugging or explicitly verifying tests. The same principle applies to `run_python_tests`; this MCP intentionally has no generic Python build validator.

The MCP exposes exactly:

- `run_python_tests(project_path=".", test_selector=None)`

Python selectors must refer to tests inside the project. Selectors beginning with `-` or `@` are rejected so they cannot be interpreted by pytest as command-line options or argument files.
- `run_java_tests(project_path=".", test_selector=None, build_system="auto")`

Java method selectors use the common `com.example.ExampleTest#method` form at the MCP boundary. Maven receives that form directly; Gradle receives the equivalent `com.example.ExampleTest.method` pattern required by `--tests`. For Maven reactor builds, modules without a matching selected test are tolerated, but the validator writes Surefire XML reports into an isolated `/output/surefire-reports` directory and verifies that at least one generated report contains a `<testcase>` entry. Arbitrary Maven log text is not used as proof of execution; otherwise the validator reports `test_selector_not_matched`.
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
- preserves safe empty directories,
- rejects symlinks, junctions and other Windows reparse points,
- rejects sockets, devices, FIFOs and other non-regular filesystem entries,
- applies per-file, total-project and snapshot-entry-count limits (`--max-snapshot-entries`, default 20,000), so many empty files cannot exhaust memory through TAR headers alone.

The TAR entries are written with container UID/GID `65532:65532`.

The snapshot boundary is designed for an untrusted project tree selected by the agent. A separate malicious host process that already has permission to mutate that workspace concurrently is outside the validator's threat model. The implementation still uses no-follow/verified file handling as defense in depth, but it does not claim to provide an atomic filesystem snapshot against an independently compromised host user/session.

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

All images must be digest-pinned and already present locally. `--pull never` is mandatory. The images must also provide a POSIX `sh`, `tar`, `cat`, `cp`, `mkdir` and `sleep`, which the fixed sandbox runner uses for lifecycle, keepalive, snapshot extraction, bounded output capture and offline-cache preparation.

### Dependency-cache contract

Every `prepare-*` command is an explicit, trusted operator action outside the MCP sandbox. It may execute project-controlled build logic with the current user's normal permissions, network access and package-manager credentials. This is intentional and is not part of the agent isolation boundary.

The promoted cache is only a credential-free offline artifact snapshot. Its project-scoped identity is stable and does not claim that the prepared dependency graph is still correct when a validator tool runs later. No semantic-equivalence guarantee is made between preparation and validation. Profiles, mirrors, dynamic versions, snapshots, platform-specific build logic, changed manifests or other project changes may make an existing cache incomplete or otherwise unsuitable.

The validator therefore does not try to parse every possible package-manager input to prove freshness. It uses the existing prepared cache offline. If required artifacts are absent, the build/install fails closed; recognized dependency-resolution failures return `dependency_cache_may_be_stale` and ask the user to rerun the matching `prepare-*` command.

### Python

The configured Python image must contain Python, pip and pytest. Project dependencies are provided by a separate prepared wheel cache.

A Windows pipx installation exposes `cli-agent-test-cache.exe` for Windows-side commands, but it is not sufficient for Python preparation. Install `cli-agent-mcp` through pipx inside WSL as well and invoke the Linux `cli-agent-test-cache` there. Calling the Windows `.exe` from a WSL shell still runs Windows Python and is rejected.

Python cache preparation **must run inside WSL**. Cache placement depends on where the MCP itself runs.

### Python preparation/image compatibility

Wheel preparation intentionally runs with the selected WSL Python interpreter so the user's normal pip/JFrog configuration and credentials stay outside the MCP and test container. Test execution, however, uses the administrator-configured pinned Docker image.

The validator does **not** attempt to derive the target image's Python wheel tags or compare them with the preparation interpreter. Matching the environments is an explicit administrator responsibility. In practice, the administrator must keep the preparation interpreter and test image compatible in at least:

- Python implementation and major/minor version when native wheels require it,
- CPU architecture,
- relevant Linux/libc/platform ABI for native wheels.

For example, preparing native CPython 3.14 wheels and testing them in a CPython 3.12 image can make the sandboxed offline `pip install` fail. The cache metadata records preparation information for diagnostics, but cache readiness intentionally does not enforce ABI equality. This is an operational compatibility constraint, not a sandbox or credential-isolation guarantee.

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

The command checks that it is actually running under WSL and refuses preparation on native Windows. It also probes the interpreter selected by `--python-command` and requires that interpreter itself to report a Linux platform, so invoking a Windows Python executable from WSL is rejected. This avoids accidentally generating Windows-only wheels for the Linux Docker sandbox. The command also prints:

```text
Python dependency preparation: WSL is required.
Prepared under WSL: yes
```

Preparation uses the current WSL Python and its normal pip configuration. Private indexes such as a company JFrog/PyPI repository can therefore remain configured in the user's WSL pip configuration; those credentials are not passed to the MCP or test container.

`--target native` is the default for every preparation command and writes below the current environment's `~/.cli-agent/dependency-cache/<type>`. Under WSL, `--target windows` resolves the Windows user profile and maps the cache to the corresponding Windows directory through the WSL mount:

```text
~/.cli-agent/dependency-cache/python/python-<sha256>/wheels
```

The same target option is available for Maven and Gradle. An explicit `--cache-root` remains available for custom layouts and overrides only the cache placement; it does not replace the target identity selection. In particular, when preparation runs in WSL for a Windows-hosted MCP that is configured with a non-default cache root, use **both** `--target windows` and `--cache-root`: `--target windows` makes the preparer compute the same Windows project identity that the Windows validator uses, while `--cache-root` selects the administrator-configured shared cache location.

For example, if the Windows MCP uses `D:\\cli-agent-dependency-cache\\python` as its Python cache root and that directory is mounted as `/mnt/d/cli-agent-dependency-cache/python` in WSL:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-python . \
  --target windows \
  --cache-root /mnt/d/cli-agent-dependency-cache/python
```

Use the analogous combination for Maven and Gradle when their Windows-hosted validator cache roots are non-default.

Python test validation requires a `requirements.txt` in the selected project root. The v1 dependency contract is deliberately narrow. Requirement and constraint files are size-checked before host-side parsing and use the validator's configured `max_file_bytes` limit, so dependency-plan validation cannot bypass the later snapshot bound: the root file and any recursive `-r/--requirement` or `-c/--constraint` files must stay inside the selected project and may contain pinned index dependencies in the form `package==version`. Compact include forms such as `-rrequirements/base.txt` and `-cconstraints.txt` are supported.

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

The Python cache identity is project-scoped and does not change when requirements files change. If the project has never been prepared, `run_python_tests` returns `reason = "dependencies_not_prepared"` and explicitly states that `cli-agent-test-cache prepare-python <project>` must be run under WSL. Running preparation always rebuilds and replaces only after a successful preparation the existing project cache. If a later offline install/test shows a recognized missing-package pattern, the tool returns `dependency_cache_may_be_stale` with a user-facing refresh hint.

### Maven

The Maven image must contain Maven. By default both the validator and the preparation CLI use:

```text
~/.cli-agent/dependency-cache/maven
```

No cache path therefore has to be added to the admin policy for each project or user. If an organization wants another location, it can configure one shared root once with `--maven-cache-root`; the user then passes the same root to `cli-agent-test-cache prepare-maven --cache-root ...`.

The cache root is never selected by the model. For each Maven project the validator calculates a stable project cache identity from the cache type plus the normalized absolute project root path. It deliberately does **not** parse POM contents, modules, parent POMs or other build inputs to decide whether dependencies are still current. Maven itself remains authoritative for that question during the offline build.

Prepare the cache as the normal user. For the normal Windows-hosted MCP case:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project
```

If a project has OS-/architecture-dependent Maven profiles or dependencies and the Linux sandbox cannot use the Windows-prepared offline cache, rerun preparation from WSL while targeting the Windows cache. Preparation always replaces the existing project cache:

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

If preparation for that Windows-hosted validator is instead run from WSL, keep the same Windows target identity and point to the WSL-mounted form of the configured root:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-maven . \
  --target windows \
  --cache-root /mnt/d/cli-agent-dependency-cache/maven
```

Preparation intentionally runs outside the MCP sandbox. Maven may use its normal user/global configuration, including the user's standard `~/.m2/settings.xml`, the selected Maven installation's global `conf/settings.xml`, active profiles, mirrors, repository credentials and project Maven configuration. Those inputs belong to the trusted preparation environment. The validator deliberately does not parse or reject them merely because the later sandbox invocation will not replay the same semantics. It builds an isolated local repository using:

```text
mvn -B -Dmaven.repo.local=<cache>/repository dependency:go-offline
mvn -B -Dmaven.repo.local=<cache>/repository -DskipTests package
```

Before promotion, the preparer removes Maven resolver-only provenance/state files such as `_remote.repositories`, `resolver-status.properties` and `*.lastUpdated`. The isolated local repository itself is the only Maven payload promoted; user/global `settings.xml`, credentials and other host configuration are not copied into the cache. The preparation command then stores only that sanitized generated repository and a small readiness marker under `maven-<sha256>`.

During a test or build the validator computes the same project cache identity. If no ready cache exists yet, it returns:

```text
reason = "dependencies_not_prepared"
```

No network fallback occurs. When the cache exists, its repository tree is validated, streamed directly from the host through Docker stdin into `/tmp/m2`, and Maven runs. If Maven reports a recognized unresolved/missing-dependency condition, the result includes `reason = "dependency_cache_may_be_stale"` and a `message_to_user` asking the user to rerun `prepare-maven`:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 test
```

or, with a selector:

```text
mvn -o -B -Dmaven.repo.local=/tmp/m2 -Dtest=<selector> -Dsurefire.failIfNoSpecifiedTests=false test
```

The Surefire flag keeps a reactor build from failing in modules that do not contain the selected test; modules with a matching test still execute it.

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

If platform-dependent Gradle build logic or dependencies make the Windows-prepared cache incomplete for the Linux sandbox, rerun preparation from WSL while targeting the Windows cache. Preparation always replaces the existing project cache:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-gradle . --target windows
```

For a fully WSL-hosted cli-agent/MCP installation, omit `--target windows`. If a Windows-hosted validator uses a non-default Gradle cache root and preparation runs from WSL, pass both `--target windows` and the WSL-mounted cache path via `--cache-root`.

The Gradle cache identity is derived only from the cache type plus the normalized absolute project root path. cli-agent deliberately does not try to statically determine which files influence Gradle dependency resolution: Gradle build scripts are executable code and may read arbitrary project files. This avoids partial parsers for `includeBuild`, `buildSrc`, version catalogs, custom properties files or other build logic. The existing cache is tried offline; recognized dependency-resolution failures ask the user to rerun `prepare-gradle`.

Preparation prefers the project's Gradle wrapper (`gradlew.bat` on Windows or `gradlew` otherwise) and falls back to Gradle from PATH. Sandbox validation intentionally uses the Gradle executable supplied by the administrator-pinned image instead of downloading/executing the wrapper distribution. The administrator is therefore responsible for choosing an image Gradle version compatible with the project's wrapper/build configuration. It uses a fresh isolated Gradle user home and executes `assemble` and `testClasses` plus an internal temporary init script that resolves all resolvable runtime classpaths named `runtimeClasspath`, `testRuntimeClasspath`, or ending in `RuntimeClasspath`. The helper init script resolves the selected runtime classpaths only. Because Gradle build scripts are executable code, preparation does not claim to prevent project-defined tests or other tasks from running; the user must trust the project before invoking `prepare-gradle`.

To support private repositories such as a company JFrog, the preparation command copies only the user's Gradle configuration files (`gradle.properties`, root init scripts and regular files in `init.d`) from the normal Gradle user home into that temporary isolated home. Before promotion, the preparer removes the copied user configuration and discards all generated Gradle user-home state except the downloaded module dependency cache at `caches/modules-2`. This also removes compiled init-script/DSL artifacts. Because Gradle repository metadata can retain repository URLs, promotion additionally rejects `resource-at-url.bin` metadata that contains URL userinfo such as `https://user:token@host/`; credentials must be supplied through Gradle's normal credential mechanisms rather than embedded in repository URLs. Older pre-sanitization Gradle caches use a previous cache schema and are rejected.

This is an intentional security boundary: user-specific `init.gradle(.kts)` / `init.d` rules are not replayed inside the sandbox. Therefore an offline build must not require those user-home init scripts for its build semantics after dependencies are already cached. If an organization needs mandatory repository/plugin-resolution logic during offline replay, that logic must be supplied separately in a credential-free, administrator-controlled form or moved into project configuration.

If no ready project cache exists, `run_java_tests(..., build_system="gradle")` returns `reason = "dependencies_not_prepared"`. There is no network fallback. A recognized offline dependency-resolution failure with an existing cache returns `reason = "dependency_cache_may_be_stale"` and a `message_to_user` asking for `prepare-gradle`.

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
gradle --offline --no-daemon --gradle-user-home /tmp/gradle assemble
```

The validator requests only the fixed `assemble` task and does not expose arbitrary Gradle tasks or options to the model. Gradle project logic can nevertheless wire other tasks, including tests, into `assemble`; any such execution occurs inside the hardened no-network sandbox rather than on the host. The host cache is never bind-mounted or writable by project code. If an organization uses a non-default cache root, configure `--gradle-cache-root` once and pass the same root to `prepare-gradle --cache-root ...`.

## Output and secret handling

Container stdout/stderr is redirected to the bounded `/output` tmpfs before it can reach the host process, then truncated/redacted before being returned to the model.

Configuration files such as `.env` intentionally remain part of the project snapshot because real test suites often require them. They are available only inside the no-network sandbox; the principal exposure path is therefore captured stdout/stderr returned to the model.

Before testing, the validator scans common configuration formats from the already verified in-memory snapshot archive. It does not reopen the original workspace paths for secret discovery. JSON is parsed with Python's JSON parser, TOML with `tomllib`, YAML with PyYAML's safe parser, `.env` with python-dotenv and Java `.properties` with javaproperties. Java properties are passed to javaproperties as the original bytes so ISO-8859-1/escape semantics are preserved instead of being damaged by an unconditional UTF-8 decode. Sensitive keys including password, secret, token and API/access key names are then traversed from the parsed data model, so escaped strings, multiline TOML/YAML values, YAML tags/anchors and properties escaping follow the format parser's semantics instead of a custom partial grammar.

If a candidate configuration file cannot be parsed and its content contains a possible sensitive-key marker, secret discovery fails closed. For `.env`, individual parser bindings flagged as errors are inspected as well; a skipped malformed binding with a sensitive-looking key also fails closed. Sensitive `.env` values that use `${...}` interpolation also fail closed rather than attempting to reproduce environment-dependent expansion semantics: the isolated validation still runs, but its captured stdout/stderr is suppressed rather than risking an incomplete redaction. Parse failures in files without such a marker do not suppress diagnostic output.

Discovered values are added to the exact multi-pattern redactor. Generic bearer-token, credential-assignment and PEM-private-key patterns remain a second defense-in-depth layer. Both discovery and redaction are explicitly bounded. If secret discovery exceeds its fixed value/count/structure budget, the validator likewise suppresses captured output. Exact multi-secret redaction uses a single-pass multi-pattern matcher rather than rescanning the whole output once per secret.

This protects against common accidental leakage while preserving normal project configuration inside the sandbox. Redaction is defense in depth, not a confidentiality guarantee against malicious test code that deliberately transforms secret material before printing it.

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


