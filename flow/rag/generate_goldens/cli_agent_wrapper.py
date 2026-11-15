"""CLI-agent adapter for the shared DeepEval benchmark.

This is deliberately a regular team AgentWrapper. The notebook imports the
class by its module path and knows nothing about cli-agent implementation,
SDK configuration, history management, or tool / Knowledge trace extraction.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def selected_knowledge_passages(trace: Any) -> list[str] | None:
    """Return actual selected retrieval text only when complete and verified."""
    if is_dataclass(trace):
        trace = asdict(trace)
    if not isinstance(trace, dict) or trace.get("truncated") is True:
        return None
    if trace.get("content_included") is not True:
        return None
    selected = trace.get("selected")
    if not isinstance(selected, (list, tuple)) or not selected:
        return None
    passages = [
        hit.get("content") if isinstance(hit, dict) else None
        for hit in selected
    ]
    if any(not isinstance(item, str) or not item.strip() for item in passages):
        return None
    return passages


class CliAgentWrapper:
    """Start SDK once; reset state before every independent Golden question."""

    def __init__(
        self,
        *,
        workspace: str = ".",
        config_file: str | None = None,
        admin_config_file: str | None = None,
        system_prompt: str | None = None,
        approve_tools: list[str] | tuple[str, ...] = (),
        include_tool_arguments: bool = False,
        redact_keys: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.config_file = Path(config_file).expanduser() if config_file else None
        self.admin_config_file = (
            Path(admin_config_file).expanduser() if admin_config_file else None
        )
        self.system_prompt = system_prompt
        self.approve_tools = frozenset(approve_tools)
        self.include_tool_arguments = include_tool_arguments
        self.redact_keys = tuple(redact_keys)
        self.agent: Any | None = None

    async def start(self) -> None:
        if self.agent is not None:
            raise RuntimeError("CLI-agent wrapper is already started")

        # Importing the wrapper requires no cli-agent installation. The SDK
        # is imported only when this particular agent is actually started.
        from cli_agent.sdk import AgentBuilder
        from cli_agent.settings.config import ensure_default_config_file

        config = self.config_file or ensure_default_config_file()
        builder = AgentBuilder().with_admin_config(path=self.admin_config_file)
        builder.with_project_config(
            path=config,
            workspace=self.workspace,
            workspace_access="none",
            response_format="text",
        )
        if self.approve_tools:
            allowed = self.approve_tools

            async def approve(name, arguments):
                return name in allowed

            builder.with_approval_callback(approve)

        if self.system_prompt is not None:
            if not isinstance(self.system_prompt, str) or not self.system_prompt.strip():
                raise ValueError("system_prompt must be nonempty text")
            builder.with_system_prompt(self.system_prompt)

        agent = (
            builder
            .with_knowledge_trace(include_content=True)
            .with_tool_trace(
                include_arguments=self.include_tool_arguments,
                redact_keys=self.redact_keys,
            )
            .build()
        )
        self.agent = agent  # enables cleanup even if start() fails
        await agent.start()

    async def answer(self, question: str) -> dict:
        if self.agent is None:
            raise RuntimeError("CLI-agent wrapper not started")
        # A new conversation for every Golden, while MCP and model resources
        # remain available. The expected answer never enters the agent.
        await self.agent.reset()
        result = await self.agent.ask(question)
        return {
            "answer": result.answer,
            "retrieval_context": selected_knowledge_passages(result.knowledge_trace),
            "tools_called": [
                {
                    "name": call.name,
                    "call_id": call.call_id,
                    "status": call.status,
                    "duration_ms": call.duration_ms,
                    **(
                        {"input_parameters": call.input_parameters}
                        if call.input_parameters is not None else {}
                    ),
                    "arguments_truncated": call.arguments_truncated,
                }
                for call in result.tool_calls
            ],
        }

    async def close(self) -> None:
        agent, self.agent = self.agent, None
        if agent is not None:
            await agent.close()
