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
- `/tmp`, `/work` and `/output` as tmpfs.

Project data is then streamed as an in-memory TAR archive through `docker exec -i ... tar -xf -` into `/work`; the real workspace is never mounted.

The Docker socket is never mounted into the test container.

The container is removed after the test run.

Docker is a strong practical isolation layer but not a virtual-machine security boundary. Native Linux containers still share the host kernel.

## Images and dependencies

All images must be digest-pinned and already present locally. `--pull never` is mandatory. The images must also provide a POSIX `sh`, `tar`, `cat`, `cp` and `mkdir`, which the fixed sandbox runner uses for lifecycle, snapshot extraction, bounded output capture and offline-cache preparation.

### Python

The configured Python image must contain Python, pip and pytest. Project dependencies are provided by a separate prepared wheel cache.

Python cache preparation **must run inside WSL**:

```bash
cd /mnt/c/dev/my-project
cli-agent-test-cache prepare-python .
```

The command checks that it is actually running under WSL and refuses preparation on native Windows. This avoids accidentally generating Windows-only wheels for the Linux Docker sandbox. The command also prints:

```text
Python dependency preparation: WSL is required.
Prepared under WSL: yes
```

Preparation uses the current WSL Python and its normal pip configuration. Private indexes such as a company JFrog/PyPI repository can therefore remain configured in the user's WSL pip configuration; those credentials are not passed to the MCP or test container.

By default, `prepare-python` resolves the Windows user's profile from WSL and writes the wheel cache to the same physical directory that the Windows MCP sees as:

```text
~/.cli-agent/dependency-cache/python/python-<sha256>/wheels
```

If this automatic mapping is unsuitable, pass an explicit WSL-visible path with `--cache-root` and configure the corresponding Windows path once with `--python-cache-root`.

The dependency key tracks common Python dependency inputs including recursively included `requirements.txt` / `requirements-dev.txt` / `requirements-test*.txt`, `pyproject.toml`, and common lock files. Source-only changes therefore keep the same cache key; dependency-file changes produce a new one.

Preparation builds wheels using pip:

```text
python -m pip wheel --wheel-dir <cache>/wheels ...
```

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

Prepare the cache as the normal user:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project
```

The default preparation root is:

```text
~/.cli-agent/dependency-cache/maven
```

Use `--cache-root` if the administrator configured a different root:

```powershell
cli-agent-test-cache prepare-maven C:\dev\my-project `
  --cache-root D:\cli-agent-dependency-cache\maven
```

Preparation intentionally runs outside the MCP sandbox. Maven can therefore use the user's normal `settings.xml`, corporate JFrog mirror and credentials. It builds an isolated local repository using:

```text
mvn -B -Dmaven.repo.local=<cache>/repository dependency:go-offline
mvn -B -Dmaven.repo.local=<cache>/repository -DskipTests test
```

The preparation command stores only the generated Maven repository and a small readiness marker under `maven-<sha256>`; it does not copy `settings.xml` or JFrog credentials into the prepared cache.

During a test the validator computes the same key. If no matching ready cache exists, it returns:

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

The host cache is never bind-mounted and is never writable by test code. Test-time modifications happen only in container tmpfs and disappear with the container.

If `--maven-cache-root` is omitted, the legacy immutable image seed at `/opt/cli-agent-test-cache/maven` remains available for compatibility.

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
--python-cache-root D:/optional/shared/cli-agent-python-cache
```

These are launch-time administrator settings, not MCP tool arguments, so the model cannot relax them.
