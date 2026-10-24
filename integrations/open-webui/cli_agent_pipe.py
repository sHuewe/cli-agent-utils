"""
title: cli-agent
author: cli-agent
version: 0.2.0
description: Local cli-agent AG-UI 1.0 integration with interactive tool approvals.
requirements: httpx>=0.27,<1
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field


# Leave room for the API's 512-message and 1 MiB request limits, including
# JSON serialization overhead. Open WebUI sends the entire chat on each turn.
MAX_HISTORY_MESSAGES = 100
MAX_HISTORY_TEXT_BYTES = 350_000
MAX_APPROVAL_ROUNDS = 16


class Pipe:
    class Valves(BaseModel):
        API_URL: str = Field(default="http://127.0.0.1:8765")
        API_TOKEN: str = Field(default="", json_schema_extra={"input": {"type": "password"}})
        TIMEOUT_SECONDS: float = Field(default=600, ge=10, le=3600)

    def __init__(self):
        self.type = "pipe"
        self.id = "cli_agent"
        self.name = "cli-agent"
        self.valves = self.Valves()
        # Only Open WebUI's backend knows these session IDs and the API token.
        self._sessions: dict[tuple[str, str], str] = {}
        self._active: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    def pipes(self):
        return [{"id": "agent", "name": "Agent"}]

    @staticmethod
    def _messages_for_agui(messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list):
            raise ValueError("Ungültiger Nachrichtenverlauf.")
        # Open WebUI's system/developer instructions never become trusted cli-agent
        # policy. Ignore tool/multimodal roles the pipe cannot round-trip.
        normal = [
            (index, item["role"], item["content"])
            for index, item in enumerate(messages)
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]
        # Do not accept stray trailing assistant messages as a new user turn.
        while normal and normal[-1][1] != "user":
            normal.pop()
        if not normal or not normal[-1][2].strip():
            raise ValueError("Keine Textnachricht des Benutzers vorhanden.")

        selected: list[dict[str, str]] = []
        total_bytes = 0
        for index, role, content in reversed(normal):
            size = len(content.encode("utf-8"))
            if size > MAX_HISTORY_TEXT_BYTES and not selected:
                raise ValueError("Benutzernachricht ist zu groß.")
            if len(selected) >= MAX_HISTORY_MESSAGES or total_bytes + size > MAX_HISTORY_TEXT_BYTES:
                break
            selected.append({"id": f"ow-{index}", "role": role, "content": content})
            total_bytes += size
        selected.reverse()
        return selected

    def _api_base(self) -> str:
        url = urlsplit(self.valves.API_URL)
        if (url.scheme != "http" or url.hostname != "127.0.0.1"
                or url.username or url.password or url.query or url.fragment
                or url.port is None or url.path not in ("", "/")):
            raise ValueError("API_URL muss http://127.0.0.1:<port> sein.")
        return self.valves.API_URL.rstrip("/")

    async def _status(self, emitter, description: str, done: bool = False):
        if emitter is not None:
            await emitter({"type": "status", "data": {
                "description": description, "done": done,
            }})

    async def _confirmation(self, interrupt: dict[str, Any], event_call) -> bool:
        """Evaluate a sanitized server-provided approval, denying by default."""
        metadata = interrupt.get("metadata")
        details = metadata.get("cli-agent") if isinstance(metadata, dict) else None
        if not isinstance(details, dict):
            details = {}
        if details.get("diff_blocked") is True or event_call is None:
            return False
        message = json.dumps({
            "toolCallId": interrupt.get("toolCallId"),
            "message": interrupt.get("message", ""),
            "details": details,
        }, ensure_ascii=False, indent=2)
        response = await event_call({
            "type": "confirmation",
            "data": {"title": "cli-agent Tool-Freigabe", "message": message[:12000]},
        })
        return response is True or (isinstance(response, dict)
                                    and response.get("confirmed") is True)

    async def _run_agui(self, client: httpx.AsyncClient, session_id: str,
                        messages: list[dict[str, str]], event_emitter, event_call) -> str:
        resume: list[dict[str, Any]] | None = None
        answer_chunks: list[str] = []
        await self._status(event_emitter, "cli-agent arbeitet …")
        for _ in range(MAX_APPROVAL_ROUNDS + 1):
            run_id = uuid.uuid4().hex
            request_body: dict[str, Any] = {
                "threadId": session_id,
                "runId": run_id,
                "protocolVersion": "1.0",
                "messages": messages,
            }
            if resume is not None:
                request_body["resume"] = resume
            outcome = None
            async with client.stream(
                "POST", "/ag-ui", json=request_body,
                headers={"Accept": "text/event-stream"},
            ) as stream:
                stream.raise_for_status()
                if "text/event-stream" not in stream.headers.get("content-type", ""):
                    raise RuntimeError("AG-UI hat keinen SSE-Stream zurückgegeben.")
                async for line in stream.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    kind = event.get("type")
                    if kind == "TEXT_MESSAGE_CONTENT":
                        answer_chunks.append(str(event.get("delta", "")))
                    elif kind == "TOOL_CALL_START":
                        await self._status(
                            event_emitter,
                            f"Tool: {event.get('toolCallName', 'unbekannt')}",
                        )
                    elif kind == "CUSTOM" and event.get("name") == "mcp_user_message":
                        value = event.get("value") or {}
                        if isinstance(value, dict):
                            await self._status(
                                event_emitter, str(value.get("content", ""))[:250],
                            )
                    elif kind == "RUN_ERROR":
                        raise RuntimeError("Agentenlauf fehlgeschlagen.")
                    elif kind == "RUN_FINISHED":
                        if event.get("runId") != run_id or event.get("threadId") != session_id:
                            raise RuntimeError("AG-UI meldet eine fremde Run-/Thread-ID.")
                        if outcome is not None:
                            raise RuntimeError("Doppeltes RUN_FINISHED im AG-UI-Stream.")
                        outcome = event.get("outcome")
            if not isinstance(outcome, dict):
                raise RuntimeError("AG-UI-Stream ohne gültiges RUN_FINISHED.")
            if outcome.get("type") == "success":
                if outcome.get("pendingToolCallIds"):
                    # Open WebUI provides no client-side tools to this pipe.
                    # Do not silently discard calls requested by a model.
                    raise RuntimeError("Frontend-Tool-Aufrufe werden von dieser Pipe nicht angeboten.")
                await self._status(event_emitter, "Fertig", done=True)
                return "".join(answer_chunks)
            if outcome.get("type") != "interrupt":
                raise RuntimeError("Unbekanntes AG-UI-Run-Ergebnis.")
            interrupts = outcome.get("interrupts")
            if (not isinstance(interrupts, list) or len(interrupts) != 1
                    or not isinstance(interrupts[0], dict)
                    or interrupts[0].get("reason") != "tool_call"
                    or not isinstance(interrupts[0].get("id"), str)
                    or not interrupts[0]["id"]):
                raise RuntimeError("Unbekannter AG-UI-Interrupt kann nicht bestätigt werden.")
            interrupt = interrupts[0]
            approved = await self._confirmation(interrupt, event_call)
            resume = [{
                "interruptId": interrupt["id"],
                "status": "resolved",
                "payload": {"approved": approved},
            }]
        raise RuntimeError("Zu viele aufeinanderfolgende AG-UI-Freigaben.")

    async def pipe(
        self, body: dict, __user__: dict | None = None,
        __event_emitter__=None, __event_call__=None,
        __metadata__: dict | None = None,
    ):
        if not self.valves.API_TOKEN:
            raise ValueError("API_TOKEN muss in den Pipe-Valves konfiguriert werden.")
        base = self._api_base()
        messages = self._messages_for_agui(body.get("messages"))
        user_id = str((__user__ or {}).get("id") or "")
        chat_id = str((__metadata__ or {}).get("chat_id") or body.get("chat_id") or "")
        persistent = bool(user_id and chat_id)
        key = (user_id, chat_id)
        if persistent:
            async with self._lock:
                if key in self._active:
                    raise RuntimeError("Dieser Open-WebUI-Chat führt bereits einen Run aus.")
                self._active.add(key)
        timeout = httpx.Timeout(self.valves.TIMEOUT_SECONDS, connect=15)
        headers = {"Authorization": f"Bearer {self.valves.API_TOKEN}"}
        sid: str | None = None
        try:
            async with httpx.AsyncClient(
                base_url=base, headers=headers, timeout=timeout, trust_env=False
            ) as client:
                sid = self._sessions.get(key) if persistent else None
                if sid is not None:
                    # The AG-UI resolver would otherwise silently *create* a new
                    # thread with this stale ID after an API restart. Preflight
                    # before any run to avoid duplicate side-effecting requests.
                    alive = await client.get(f"/sessions/{sid}/context")
                    if alive.status_code == 404:
                        self._sessions.pop(key, None)
                        sid = None
                    else:
                        alive.raise_for_status()
                if sid is None:
                    response = await client.post("/sessions")
                    response.raise_for_status()
                    sid = response.json()["session_id"]
                    if persistent:
                        self._sessions[key] = sid
                try:
                    return await self._run_agui(
                        client, sid, messages, __event_emitter__, __event_call__
                    )
                finally:
                    if not persistent and sid is not None:
                        await client.delete(f"/sessions/{sid}")
        finally:
            if persistent:
                async with self._lock:
                    self._active.discard(key)
