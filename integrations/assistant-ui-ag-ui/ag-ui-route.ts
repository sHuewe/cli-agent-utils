/**
 * Same-origin reverse proxy for the unmodified official assistant-ui AG-UI
 * client. Auth and networking live on the server, never in browser JavaScript.
 * No event conversion, tool dispatching or cli-agent-specific run protocol.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 1024 * 1024;
// This is a loopback-only, single-user test UI. Never derive the trusted
// origin from client-controlled Host / X-Forwarded-* request headers.
const UI_ORIGIN = "http://127.0.0.1:3000";
const UI_HOST = new URL(UI_ORIGIN).host;

export async function POST(request: Request): Promise<Response> {
  // A foreign webpage can send a "simple" POST with text/plain without
  // preflight. CORS prevents reading a response, not triggering the agent.
  // Refuse absent/null/foreign origins *before* adding the service token.
  if (
    request.headers.get("origin") !== UI_ORIGIN ||
    request.headers.get("host") !== UI_HOST
  ) {
    return new Response("Forbidden origin or host", { status: 403 });
  }

  // Never silently upgrade a CORS-safelisted text/plain/form payload to
  // application/json on the authenticated upstream request.
  const mime = request.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase();
  if (mime !== "application/json") {
    return new Response("Content-Type application/json required", { status: 415 });
  }

  const endpoint =
    process.env.CLI_AGENT_API_URL ?? "http://127.0.0.1:8765/ag-ui";
  const token = process.env.CLI_AGENT_API_TOKEN;

  if (!token) {
    return new Response("Missing CLI_AGENT_API_TOKEN", { status: 503 });
  }

  // The integration is intentionally local-only. Avoid leaking the service
  // token to an arbitrary hostname through a misconfigured environment.
  let url: URL;
  try {
    url = new URL(endpoint);
  } catch {
    return new Response("Invalid CLI_AGENT_API_URL", { status: 503 });
  }
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    url.pathname !== "/ag-ui" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    return new Response(
      "CLI_AGENT_API_URL must be http://127.0.0.1:<port>/ag-ui",
      { status: 503 },
    );
  }

  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_BODY_BYTES) {
    return new Response("Request too large", { status: 413 });
  }

  try {
    const upstream = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        Authorization: `Bearer ${token}`,
      },
      body,
      cache: "no-store",
      signal: request.signal,
    });

    // Forward AG-UI's SSE bytes and HTTP errors without reinterpreting them.
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "text/event-stream",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return new Response("Local AG-UI endpoint unreachable", { status: 502 });
  }
}
