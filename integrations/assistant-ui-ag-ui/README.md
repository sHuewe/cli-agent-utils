# Independent AG-UI frontend: assistant-ui Docker smoke test

This is a deliberately **independent client** of the AG-UI 1.0 wire protocol
implemented by [cli-agent](https://github.com/sHuewe/cli-agent). It uses the
official [assistant-ui `with-ag-ui` example](https://github.com/assistant-ui/assistant-ui/tree/main/examples/with-ag-ui)
and its `@ag-ui/client` `HttpAgent` / `@assistant-ui/react-ag-ui`
runtime. There is **no cli-agent-specific React adapter**. The only added
server code is a small same-origin HTTP/SSE proxy to keep the API token
out of the browser and avoid CORS.

This setup is for **Linux Docker Engine** using `network_mode: host`.
The CLI API and the UI container must run on **the same host**.

## Start

1. Start a working cli-agent API locally (AG-UI 1.0 version, PR #241 or newer):

   ```bash
   cli-agent-api --config config.toml --workspace . --with-os-read --port 8765
   ```

   Keep it bound to `127.0.0.1`. Note the service bearer token printed on
   startup. Use your own existing model/MCP configuration.

2. From `integrations/assistant-ui-ag-ui`, prepare the token and build:

   ```bash
   cp .env.example .env
   # Edit .env: set CLI_AGENT_API_TOKEN to the service token (without "Bearer ").
   docker compose build
   docker compose up -d
   ```

3. Browse to **http://127.0.0.1:3000** and send a message. Check
   `docker compose logs -f assistant-ui` if the UI cannot reach the API.
   Cleanup: `docker compose down`.

The token-bearing proxy **requires** the exact browser origin and host
`http://127.0.0.1:3000` and accepts only `Content-Type: application/json`.
Requests without an Origin, from another Origin (including `localhost`
instead of `127.0.0.1`), or with a different Host are rejected before the
service token is attached. Do not place the UI behind a public reverse proxy
without a separate authentication and CSRF design.

Run the independent security tests using Node 22 or newer:

```bash
node --experimental-strip-types --test ag-ui-route.test.mjs
```

The container binds the Next.js UI to **127.0.0.1:3000** with the host
network. Do **not** add `ports:`, expose the cli-agent API on `0.0.0.0`,
or forward the browser token to the API. This is a single-user smoke-test
deployment; there is no separate browser login. Never publish port 3000 or
the service token to untrusted users.

## What to validate

- Send multiple messages in one thread; new threads should have separate
  state (the example's thread list is in-memory, not persisted on restart).
- Try an MCP read-only tool: backend tool events should be displayed.
- For approvals, run a dedicated test with write capability and explicitly
  approve **and** deny once. Confirm that no operation runs before approval.
- Try the official sample `browser_alert` frontend tool and verify the
  result roundtrip.
- Compare the observed client behavior against the native cli-agent UI.

**Limits:** We did not run a Docker build or an end-to-end LLM/MCP test in
this environment. The official assistant-ui AG-UI adapter documents
streaming, frontend tool handoff and interrupt support, but interrupt
handling is currently experimental in that client. A failing approval
does **not** establish that cli-agent violates AG-UI. The official example
and dependencies are resolved during build; for a stable regression
fixture, retain the built image by digest and update it deliberately.
The `assistant-ui` scaffold CLI is pinned to `0.0.122` for initial testing;
its transitive packages and source template are not fully locked here.

## Architecture

```
Browser localhost:3000
  -> assistant-ui HttpAgent (standard RunAgentInput)
  -> Next.js POST /api/ag-ui (same-origin proxy; inserts server-side token)
  -> cli-agent-api 127.0.0.1:8765/ag-ui (AG-UI HTTP/SSE)
```

Open WebUI is an **alternative** UI, not part of this Compose file.
Its pipe under `../open-webui/` has now been migrated to `POST /ag-ui`
with AG-UI 1.0 HTTP/SSE, including human approval interrupts and resume.
Open WebUI does not currently expose a confirmed native AG-UI client
configuration, so the pipe remains a **custom Open-WebUI adapter**, not
proof that an unrelated AG-UI frontend works without an adapter.
