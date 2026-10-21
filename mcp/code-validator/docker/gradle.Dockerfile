# syntax=docker/dockerfile:1

# Build a validator-compatible Gradle image without inheriting the official
# Gradle image's declared /home/gradle/.gradle VOLUME.
#
# Examples:
#   docker build -f mcp/code-validator/docker/gradle.Dockerfile \
#     --build-arg JAVA_VERSION=8 --build-arg GRADLE_VERSION=8.14.5 \
#     -t cli-agent-gradle:8.14.5-jdk8 .
#
#   docker build -f mcp/code-validator/docker/gradle.Dockerfile \
#     --build-arg JAVA_VERSION=21 --build-arg GRADLE_VERSION=9.8.0 \
#     -t cli-agent-gradle:9.8.0-jdk21 .
#
#   docker build -f mcp/code-validator/docker/gradle.Dockerfile \
#     --build-arg JAVA_VERSION=25 --build-arg GRADLE_VERSION=9.8.0 \
#     -t cli-agent-gradle:9.8.0-jdk25 .

ARG JAVA_VERSION=21
ARG GRADLE_VERSION=9.8.0

FROM gradle:${GRADLE_VERSION}-jdk${JAVA_VERSION} AS gradle_source

FROM eclipse-temurin:${JAVA_VERSION}-jdk

COPY --from=gradle_source /opt/gradle /opt/gradle

ENV GRADLE_HOME=/opt/gradle
ENV PATH="${GRADLE_HOME}/bin:${PATH}"

# Fail the image build if the base image ever stops providing a command that
# the validator relies on.
RUN set -eux; \
    for command in sh tar cat cp mkdir sleep; do \
        command -v "${command}"; \
    done; \
    java -version; \
    gradle --version

WORKDIR /work
