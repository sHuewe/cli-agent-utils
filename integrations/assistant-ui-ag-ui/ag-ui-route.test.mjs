// Node 22+ zero-dependency regression tests for the Next.js route handler.
// Run with: node --experimental-strip-types --test ag-ui-route.test.mjs
import assert from "node:assert/strict";
import { test, mock } from "node:test";
import { POST } from "./ag-ui-route.ts";

const host = "127.0.0.1:3000";
const url = "http://127.0.0.1:3000/api/ag-ui";
process.env.CLI_AGENT_API_URL = "http://127.0.0.1:8765/ag-ui";
process.env.CLI_AGENT_API_TOKEN = "test-secret";

function request({ origin = "http://127.0.0.1:3000", type = "application/json", hostHeader = host } = {}) {
  const headers = { host: hostHeader };
  if (origin !== null) headers.origin = origin;
  if (type !== null) headers["content-type"] = type;
  return new Request(url, {
    method: "POST",
    headers,
    body: '{"threadId":"thread","runId":"run","messages":[]}',
  });
}

test("rejects hostile, absent, and null origins before forwarding", async () => {
  const fetched = mock.method(globalThis, "fetch", async () => { throw Error("must not forward"); });
  try {
    for (const origin of ["https://evil.example", "http://localhost:3000", "null", null]) {
      assert.equal((await POST(request({origin}))).status, 403);
    }
    assert.equal(fetched.mock.callCount(), 0);
  } finally {
    fetched.mock.restore();
  }
});

test("rejects host mismatches even with forged matching Origin", async () => {
  const fetched = mock.method(globalThis, "fetch", async () => { throw Error("must not forward"); });
  try {
    for (const hostHeader of ["evil.example", "localhost:3000", "127.0.0.1:9999"]) {
      assert.equal((await POST(request({hostHeader}))).status, 403);
    }
    assert.equal(fetched.mock.callCount(), 0);
  } finally {
    fetched.mock.restore();
  }
});

test("rejects cross-site simple content types and missing JSON content type", async () => {
  const fetched = mock.method(globalThis, "fetch", async () => { throw Error("must not forward"); });
  try {
    for (const type of ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", null]) {
      assert.equal((await POST(request({type}))).status, 415);
    }
    assert.equal(fetched.mock.callCount(), 0);
  } finally {
    fetched.mock.restore();
  }
});

test("same-origin JSON is forwarded as AG-UI SSE with server-only token", async () => {
  const fetched = mock.method(globalThis, "fetch", async (upstream, options) => {
    assert.equal(upstream.href, "http://127.0.0.1:8765/ag-ui");
    assert.equal(options.headers.Authorization, "Bearer test-secret");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.equal(new TextDecoder().decode(options.body), '{"threadId":"thread","runId":"run","messages":[]}');
    return new Response('data: {"type":"RUN_FINISHED"}\n\n', {
      headers: {"content-type":"text/event-stream"},
    });
  });
  try {
    const res = await POST(request({type:"application/json; charset=utf-8"}));
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("content-type"), "text/event-stream");
    assert.match(await res.text(), /RUN_FINISHED/);
    assert.equal(fetched.mock.callCount(), 1);
  } finally {
    fetched.mock.restore();
  }
});
