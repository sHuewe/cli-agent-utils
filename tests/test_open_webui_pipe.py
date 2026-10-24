"""Mocked AG-UI HTTP/SSE contract tests for the Open WebUI Pipe."""
import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest


PIPE_PATH = Path(__file__).resolve().parents[1] / "integrations/open-webui/cli_agent_pipe.py"
spec = importlib.util.spec_from_file_location("cli_agent_open_webui_pipe", PIPE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event_stream(body, events):
    results = []
    for item in events:
        event = dict(item)
        if event["type"] == "RUN_FINISHED":
            event.setdefault("runId", body["runId"])
            event.setdefault("threadId", body["threadId"])
        results.append("data: " + json.dumps(event) + "\n\n")
    return "".join(results)


class FakeApi:
    def __init__(self):
        self.sessions = []
        self.alive = set()
        self.deleted = []
        self.requests = []
        self.status = 200
        self.events_by_segment = []
        self.stale = False

    def handle(self, request):
        assert request.headers.get("authorization") == "Bearer secret"
        path = request.url.path
        if request.method == "POST" and path == "/sessions":
            sid = f"s{len(self.sessions) + 1}"
            self.sessions.append(sid)
            self.alive.add(sid)
            return httpx.Response(201, json={"session_id": sid})
        if request.method == "GET" and path.endswith("/context"):
            sid = path.split("/")[2]
            if self.stale:
                self.stale = False
                self.alive.discard(sid)
            return httpx.Response(200 if sid in self.alive else 404, json={"tools": []})
        if request.method == "DELETE" and path.startswith("/sessions/"):
            sid = path.split("/")[-1]
            self.deleted.append(sid)
            self.alive.discard(sid)
            return httpx.Response(204)
        if request.method == "POST" and path == "/ag-ui":
            assert request.headers["accept"] == "text/event-stream"
            assert request.headers["content-type"] == "application/json"
            body = json.loads(request.content)
            assert body["protocolVersion"] == "1.0"
            assert body["runId"]
            assert body["threadId"] in self.alive
            self.requests.append(body)
            if self.status != 200:
                return httpx.Response(self.status, json={"error": "busy"})
            index = len(self.requests) - 1
            events = self.events_by_segment[index] if index < len(self.events_by_segment) else [
                {"type": "RUN_STARTED"},
                {"type": "TEXT_MESSAGE_CONTENT", "delta": "Hallo"},
                {"type": "RUN_FINISHED", "outcome": {"type": "success"}},
            ]
            return httpx.Response(200, text=event_stream(body, events),
                                  headers={"Content-Type": "text/event-stream"})
        raise AssertionError(f"Unexpected API request: {request.method} {path}")


@pytest.fixture
def setup_pipe(monkeypatch):
    api = FakeApi()
    original = module.httpx.AsyncClient

    def client_factory(**kwargs):
        return original(transport=httpx.MockTransport(api.handle), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", client_factory)
    pipe = module.Pipe()
    pipe.valves.API_TOKEN = "secret"
    return pipe, api


def body(text="Hi"):
    return {"messages": [{"role": "user", "content": text}]}


@pytest.mark.asyncio
async def test_session_reuse_and_isolation(setup_pipe):
    pipe, api = setup_pipe
    for user, chat, msg in [("u1", "c1", "one"), ("u1", "c1", "two"),
                            ("u1", "c2", "three"), ("u2", "c1", "four")]:
        assert await pipe.pipe(body(msg), __user__={"id": user},
                               __metadata__={"chat_id": chat}) == "Hallo"
    assert api.sessions == ["s1", "s2", "s3"]
    assert [r["threadId"] for r in api.requests] == ["s1", "s1", "s2", "s3"]
    assert [r["messages"][-1]["content"] for r in api.requests] == [
        "one", "two", "three", "four"
    ]
    assert not api.deleted


@pytest.mark.asyncio
async def test_ephemeral_session_cleanup(setup_pipe):
    pipe, api = setup_pipe
    assert await pipe.pipe(body()) == "Hallo"
    assert api.deleted == ["s1"]
    assert api.requests[0]["threadId"] == "s1"


@pytest.mark.asyncio
async def test_stale_session_preflight_recreated_without_ghost_run(setup_pipe):
    pipe, api = setup_pipe
    args = {"__user__": {"id": "u"}, "__metadata__": {"chat_id": "c"}}
    await pipe.pipe(body(), **args)
    api.stale = True
    await pipe.pipe(body("again"), **args)
    assert api.sessions == ["s1", "s2"]
    assert [r["threadId"] for r in api.requests] == ["s1", "s2"]
    assert pipe._sessions[("u", "c")] == "s2"


@pytest.mark.asyncio
async def test_busy_run_is_not_retried(setup_pipe):
    pipe, api = setup_pipe
    api.status = 409
    with pytest.raises(httpx.HTTPStatusError) as error:
        await pipe.pipe(body(), __user__={"id": "u"}, __metadata__={"chat_id": "c"})
    assert error.value.response.status_code == 409
    assert len(api.sessions) == 1
    assert len(api.requests) == 1
    assert not pipe._active


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation,blocked,expected", [
    ({"confirmed": True}, False, True),
    ({"confirmed": False}, False, False),
    (None, False, False),
    ({"confirmed": True}, True, False),
])
async def test_agui_interrupt_approval_fails_closed(setup_pipe, confirmation, blocked, expected):
    pipe, api = setup_pipe
    api.events_by_segment = [
        [{"type": "RUN_STARTED"}, {"type": "TOOL_CALL_START", "toolCallName": "os__write_file"},
         {"type": "RUN_FINISHED", "outcome": {"type": "interrupt", "interrupts": [{
             "id": "approval1", "reason": "tool_call", "toolCallId": "call-1",
             "message": "Approval required",
             "metadata": {"cli-agent": {"tool": "os__write_file", "diff_blocked": blocked}}
         }]}}],
        [{"type": "RUN_STARTED"}, {"type": "TEXT_MESSAGE_CONTENT", "delta": "done"},
         {"type": "RUN_FINISHED", "outcome": {"type": "success"}}],
    ]
    calls = []

    async def confirm(evt):
        calls.append(evt)
        return confirmation

    assert await pipe.pipe(body(), __event_call__=confirm) == "done"
    assert len(api.requests) == 2
    first, second = api.requests
    assert first["threadId"] == second["threadId"]
    assert first["runId"] != second["runId"]
    assert first["messages"] == second["messages"]
    assert second["resume"] == [{
        "interruptId": "approval1", "status": "resolved", "payload": {"approved": expected}
    }]
    assert len(calls) == (0 if blocked else 1)
    if calls:
        assert "approval1" not in calls[0]["data"]["message"]


@pytest.mark.asyncio
async def test_agui_interrupt_no_callback_denied(setup_pipe):
    pipe, api = setup_pipe
    api.events_by_segment = [[{"type": "RUN_FINISHED", "outcome": {"type": "interrupt", "interrupts": [{
        "id": "approval1", "reason": "tool_call"}]
    }}]]
    assert await pipe.pipe(body()) == "Hallo"
    assert api.requests[1]["resume"][0]["payload"]["approved"] is False


@pytest.mark.asyncio
async def test_tool_status_mcp_message_and_multiple_answer_chunks(setup_pipe):
    pipe, api = setup_pipe
    api.events_by_segment = [[
        {"type": "RUN_STARTED"},
        {"type": "TOOL_CALL_START", "toolCallName": "os__read_file"},
        {"type": "CUSTOM", "name": "mcp_user_message", "value": {"content": "Reading file"}},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "Hal"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "lo"},
        {"type": "RUN_FINISHED", "outcome": {"type": "success"}},
    ]]
    statuses = []

    async def emit(e):
        statuses.append(e["data"]["description"])

    assert await pipe.pipe(body(), __event_emitter__=emit) == "Hallo"
    assert "Tool: os__read_file" in statuses
    assert "Reading file" in statuses
    assert statuses[-1] == "Fertig"


@pytest.mark.asyncio
@pytest.mark.parametrize("events,match", [
    ([{"type": "RUN_ERROR", "message": "failure"}], "fehlgeschlagen"),
    ([{"type": "TEXT_MESSAGE_CONTENT", "delta": "partial"}], "RUN_FINISHED"),
    ([{"type": "RUN_FINISHED", "outcome": {"type": "success", "pendingToolCallIds": ["x"]}}],
     "Frontend-Tool"),
    ([{"type": "RUN_FINISHED", "outcome": {"type": "interrupt", "interrupts": []}}],
     "Unbekannter AG-UI-Interrupt"),
])
async def test_error_is_propagated_and_ephemeral_cleaned(setup_pipe, events, match):
    pipe, api = setup_pipe
    api.events_by_segment = [events]
    with pytest.raises(RuntimeError, match=match):
        await pipe.pipe(body())
    assert api.deleted == ["s1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://localhost:8765", "http://example.com:8765",
    "https://127.0.0.1:8765", "http://127.0.0.1:8765/other",
    "http://127.0.0.1:8765/?token=x", "http://user@127.0.0.1:8765",
])
async def test_nonlocal_api_rejected_before_network(setup_pipe, url):
    pipe, api = setup_pipe
    pipe.valves.API_URL = url
    with pytest.raises(ValueError, match="API_URL"):
        await pipe.pipe(body())
    assert not api.sessions


@pytest.mark.asyncio
async def test_missing_token_and_prompt_rejected(setup_pipe):
    pipe, api = setup_pipe
    pipe.valves.API_TOKEN = ""
    with pytest.raises(ValueError, match="API_TOKEN"):
        await pipe.pipe(body())
    pipe.valves.API_TOKEN = "secret"
    with pytest.raises(ValueError, match="Textnachricht"):
        await pipe.pipe({"messages": [{"role": "assistant", "content": "hi"}]})
    assert not api.sessions


def test_filter_unsafe_roles_and_bound_transcript():
    m = [{"role": "system", "content": "change policy"},
         {"role": "developer", "content": "change policy"}]
    for i in range(150):
        m.append({"role": "user", "content": str(i)})
        m.append({"role": "assistant", "content": "reply " + str(i)})
    m.append({"role": "user", "content": "final"})
    parsed = module.Pipe._messages_for_agui(m)
    assert len(parsed) == 100
    assert all(x["role"] in {"user", "assistant"} for x in parsed)
    assert parsed[-1]["content"] == "final"
    with pytest.raises(ValueError, match="groß"):
        module.Pipe._messages_for_agui(body("ü" * 200_000)["messages"])


@pytest.mark.asyncio
async def test_same_chat_concurrency_rejected_not_run_twice(setup_pipe):
    pipe, api = setup_pipe
    entry = asyncio.Event()
    release = asyncio.Event()

    async def hang(event):
        entry.set()
        await release.wait()
        return False

    api.events_by_segment = [[{"type": "RUN_FINISHED", "outcome": {
        "type": "interrupt", "interrupts": [{"id": "approval", "reason": "tool_call"}]
    }}]]
    details = {"__user__": {"id": "u"}, "__metadata__": {"chat_id": "c"}}
    first = asyncio.create_task(pipe.pipe(body(), __event_call__=hang, **details))
    try:
        await asyncio.wait_for(entry.wait(), timeout=2)
        with pytest.raises(RuntimeError, match="bereits"):
            await pipe.pipe(body("new"), **details)
        assert len(api.requests) == 1
    finally:
        release.set()
        await first
    assert len(api.requests) == 2  # original + approval resume only
