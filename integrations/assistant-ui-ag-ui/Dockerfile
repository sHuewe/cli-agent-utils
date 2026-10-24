# Smoke-test container based on the *official* assistant-ui AG-UI example.
# No cli-agent-specific transport adapter is installed in the React client.
FROM node:22-bookworm-slim AS build
WORKDIR /work

# The scaffold CLI is versioned; the example and npm dependencies are obtained
# during the Docker build. Pin the resulting image digest for repeatable tests.
ARG ASSISTANT_UI_CLI_VERSION=0.0.122
ENV CI=1
RUN npx --yes "assistant-ui@${ASSISTANT_UI_CLI_VERSION}" create ui \
    --example with-ag-ui --use-npm --skip-install

# Only same-origin routing/auth is custom. React keeps using HttpAgent and
# useAgUiRuntime from the upstream template.
COPY ag-ui-route.ts /tmp/ag-ui-route.ts
RUN mkdir -p /work/ui/app/api/ag-ui \
    && cp /tmp/ag-ui-route.ts /work/ui/app/api/ag-ui/route.ts

WORKDIR /work/ui
RUN npm install --no-audit --no-fund
# NEXT_PUBLIC_* is baked into the static browser bundle at build time.
ENV NEXT_PUBLIC_AGUI_AGENT_URL=/api/ag-ui
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    CLI_AGENT_API_URL=http://127.0.0.1:8765/ag-ui
COPY --from=build /work/ui /app

# The localhost binding below is essential when Docker shares the host network.
# Docker host-network mode ignores -p/ports mappings.
USER node
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "127.0.0.1", "-p", "3000"]
