# Validator Docker images

The Code-Validator does not download or modify its execution images at runtime. Administrators provide three immutable images:

- Python: Python, `pip`, and `pytest`
- Maven: a JDK plus Maven
- Gradle: a JDK plus Gradle

All validator images must also contain a POSIX `sh` and the utilities `tar`, `cat`, `cp`, `mkdir`, and `sleep`. Images are started with a read-only root filesystem and with writable tmpfs mounts only at `/tmp`, `/work`, and `/output`.

The examples below are starting points for building or selecting images. Production/admin configuration must still use a complete `@sha256:<digest>` reference, not a mutable tag.

## Python

A small Debian-based Python image is a convenient base. Avoid relying on an image that does not already contain the utilities required by the sandbox.

Example:

```dockerfile
FROM python:3.12-slim-bookworm

RUN python -m pip install --no-cache-dir pytest \
    && for command in sh tar cat cp mkdir sleep; do command -v "$command"; done \
    && python --version \
    && python -m pytest --version
```

Build it with a local tag first:

```bash
docker build -t cli-agent-python-tests:3.12 -f Dockerfile .
```

The Python version and platform ABI of the validator image should be compatible with the Linux interpreter used by `cli-agent-dependency-cache prepare-python`, especially when native wheels are present.

## Maven / Java

For Maven, the official Maven images are suitable starting points because they already combine Maven with Eclipse Temurin JDKs. As of this documentation update, Maven 3.9.16 images are available for the following common Java versions:

| Java/JDK | Suggested image tag |
| --- | --- |
| 8 | `maven:3.9.16-eclipse-temurin-8` |
| 11 | `maven:3.9.16-eclipse-temurin-11` |
| 17 | `maven:3.9.16-eclipse-temurin-17` |
| 21 | `maven:3.9.16-eclipse-temurin-21` |
| 25 | `maven:3.9.16-eclipse-temurin-25` |

Use the JDK version that matches the project/build assumptions. A project may intentionally compile for an older Java target while Maven itself runs on a newer JDK; that is a project-level decision and is not inferred by the validator.

For local evaluation, a normal pull is sufficient:

```bash
docker pull maven:3.9.16-eclipse-temurin-21
```

Before configuring the MCP, resolve and approve the immutable digest and configure the resulting `maven@sha256:...` reference.

## Gradle / Java

The official Gradle images are useful as build sources, but the Code-Validator should not use them directly. The official image declares `/home/gradle/.gradle` as a Docker `VOLUME`, while the validator deliberately rejects images that declare volumes because they can introduce unexpected mounts.

The repository therefore provides [`docker/gradle.Dockerfile`](../docker/gradle.Dockerfile). It copies the Gradle installation from the official image into a clean Eclipse Temurin image. Docker metadata such as the source image's `VOLUME` declaration is not inherited by the final stage.

Both Java and Gradle versions are build arguments:

```bash
docker build \
  -f mcp/code-validator/docker/gradle.Dockerfile \
  --build-arg JAVA_VERSION=21 \
  --build-arg GRADLE_VERSION=9.8.0 \
  -t cli-agent-gradle:9.8.0-jdk21 .
```

Recommended starting points based on the Gradle JVM compatibility matrix are:

| JDK used to run Gradle | Suggested Gradle version | Example build arguments |
| --- | --- | --- |
| 8 | 8.14.5 | `JAVA_VERSION=8 GRADLE_VERSION=8.14.5` |
| 11 | 8.14.5 | `JAVA_VERSION=11 GRADLE_VERSION=8.14.5` |
| 17 | 9.8.0 | `JAVA_VERSION=17 GRADLE_VERSION=9.8.0` |
| 21 | 9.8.0 | `JAVA_VERSION=21 GRADLE_VERSION=9.8.0` |
| 25 | 9.8.0 | `JAVA_VERSION=25 GRADLE_VERSION=9.8.0` |

These are not project compatibility guarantees. The validator intentionally executes the `gradle` binary installed in the administrator image instead of the project's Gradle Wrapper. Choose a Gradle version that is compatible with the project's wrapper/build logic. In particular:

- Java 8 and 11 can run Gradle only through the 8.14.x line, not Gradle 9.x.
- Java 17 can run Gradle 7.3 and newer.
- Java 21 requires Gradle 8.5 or newer to run Gradle itself.
- Java 25 requires Gradle 9.1 or newer to run Gradle itself.

A project that targets an older Java bytecode level may still run Gradle on a newer JDK by using normal Java/Gradle compiler settings or toolchains. If the project requires an additional JDK toolchain inside the no-network sandbox, that JDK must already be included in the administrator image; the validator does not download toolchains.

Official references:

- Gradle Java compatibility matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle Docker images: https://docs.gradle.org/current/userguide/docker.html
- Maven official image: https://hub.docker.com/_/maven/

## Verify an image before configuring it

The validator checks the effective container policy at runtime, but an administrator can catch common image problems earlier.

Check the required commands:

```bash
docker run --rm --entrypoint sh <image> -c \
  'for c in sh tar cat cp mkdir sleep; do command -v "$c" || exit 1; done'
```

Check that the image itself does not declare volumes:

```bash
docker image inspect <image> --format '{{json .Config.Volumes}}'
```

For a validator-compatible image this should be `null` or otherwise empty.

Also verify the language/build tool:

```bash
docker run --rm --entrypoint sh <python-image> -c 'python --version && python -m pytest --version'
docker run --rm --entrypoint sh <maven-image> -c 'java -version && mvn --version'
docker run --rm --entrypoint sh <gradle-image> -c 'java -version && gradle --version'
```

## Digest pinning and local testing

The Code-Validator accepts only references of the form:

```text
registry.example/image@sha256:<64-hex-digest>
```

A mutable tag such as `cli-agent-gradle:9.8.0-jdk21` is useful while building, but it cannot be passed to the MCP.

For upstream images, pull the chosen tag and use its approved repository digest. For custom images, the most reproducible local workflow is to push the image to a local/private registry and configure the resulting repository digest. For example:

```bash
docker tag cli-agent-gradle:9.8.0-jdk21 localhost:5000/cli-agent-gradle:9.8.0-jdk21
docker push localhost:5000/cli-agent-gradle:9.8.0-jdk21
docker image inspect localhost:5000/cli-agent-gradle:9.8.0-jdk21 \
  --format '{{json .RepoDigests}}'
```

Then use the returned `localhost:5000/cli-agent-gradle@sha256:...` reference in the administrator configuration. The image must already be present in the Docker daemon used by the validator because runtime execution uses `--pull never`.
