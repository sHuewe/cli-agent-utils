"""CLI-agent adapter for the shared DeepEval benchmark.

This is deliberately a regular team AgentWrapper. The notebook imports the
class by its module path and knows nothing about cli-agent implementation,
SDK configuration, history management, or tool / Knowledge trace extraction.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

# All admin permissions for this benchmark are defined HERE, not loaded
# from /etc/cli-agent/admin_config.toml or Windows ProgramData.
# Replace example names with the EXACT hosts needed for your model and MCPs.
# Network access fails closed until those allowlists are configured.
ADMIN_MODEL_ALLOWED_HOSTS = ("REPLACE_WITH_MODEL_HOST.example",)
ADMIN_MCP_ALLOWED_HOSTS = ("REPLACE_WITH_MCP_HOST.example",)
ADMIN_WEB_ALLOWED_HOSTS: tuple[str, ...] = ()
ADMIN_MODEL_CREDENTIALS: tuple = ()
ADMIN_TRUSTED_SERVERS: tuple = ()
ADMIN_WEB_PROVIDERS: tuple = ()

# Templates: deliberately not real document stores, credentials or services.
# Pass either mapping to the wrapper constructor (or supply custom values).
# Set okf=None / rag=None to explicitly disable that subsystem.
EXAMPLE_OKF = {
    "repository": "REPLACE_WITH_OKF_REPOSITORY",
    "required": True,
}
EXAMPLE_RAG = {
    # SQLite hybrid RAG requires OKF; alternatively use mode="chroma".
    "mode": "okf",
    "database": "REPLACE_WITH_VECTOR_DATABASE",
    "provider": "ollama",
    "model": "REPLACE_WITH_EMBEDDING_MODEL",
    "base_url": "http://REPLACE_WITH_EMBEDDING_HOST.example:11434",
    "search_limit": 5,
    "required": True,
}


def _knowledge_config(value: dict | None, cls: type, field: str):
    """Fail on malformed mappings, instead of accepting partial silent fallback."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be a dictionary or None")
    allowed = set(cls.__dataclass_fields__)
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unknown {field} keys: {sorted(unknown)}")
    if any(isinstance(item, str) and "REPLACE_WITH_" in item for item in value.values()):
        raise ValueError(
            f"{field} still contains example placeholders. "
            "Set real values in the wrapper kwargs or use None to disable it."
        )
    return cls(**value)


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
        okf: dict | None = EXAMPLE_OKF,
        rag: dict | None = EXAMPLE_RAG,
        system_prompt: str | None = None,
        approve_tools: list[str] | tuple[str, ...] = (),
        tool_allowlist: list[str] | tuple[str, ...] | None = None,
        max_tool_calls: int | None = None,
        max_additional_knowledge_calls: int | None = None,
        workspace_access: str = "none",
        include_tool_arguments: bool = False,
        redact_keys: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.config_file = Path(config_file).expanduser() if config_file else None
        # Copy the templates so no instance can mutate another's settings.
        self.okf = dict(okf) if isinstance(okf, dict) else okf
        self.rag = dict(rag) if isinstance(rag, dict) else rag
        self.system_prompt = system_prompt
        self.approve_tools = frozenset(approve_tools)
        self.tool_allowlist = tool_allowlist
        self.max_tool_calls = max_tool_calls
        self.max_additional_knowledge_calls = max_additional_knowledge_calls
        self.workspace_access = workspace_access
        self.include_tool_arguments = include_tool_arguments
        self.redact_keys = tuple(redact_keys)
        self.agent: Any | None = None

    async def start(self) -> None:
        if self.agent is not None:
            raise RuntimeError("CLI-agent wrapper is already started")

        # Importing the wrapper requires no cli-agent installation. The SDK
        # is imported only when this particular agent is actually started.
        from cli_agent.sdk import AgentBuilder
        from cli_agent.settings.config import (
            OkfConfig, VectorKnowledgeConfig, ensure_default_config_file,
        )

        # Explicit overrides begin with AdminConfig()'s restrictive policy.
        # Crucially, no path is passed and no no-arg with_admin_config()
        # call is made: those would read the machine-wide admin policy.
        builder = AgentBuilder().with_admin_config(
            model_allowed_hosts=list(ADMIN_MODEL_ALLOWED_HOSTS),
            mcp_allowed_hosts=list(ADMIN_MCP_ALLOWED_HOSTS),
            web_allowed_hosts=list(ADMIN_WEB_ALLOWED_HOSTS),
            model_credentials=ADMIN_MODEL_CREDENTIALS,
            trusted_servers=ADMIN_TRUSTED_SERVERS,
            web_providers=ADMIN_WEB_PROVIDERS,
        )
        config = self.config_file or ensure_default_config_file()
        builder.with_project_config(
            path=config,
            workspace=self.workspace,
            workspace_access=self.workspace_access,
            **({"tool_allowlist": self.tool_allowlist} if self.tool_allowlist is not None else {}),
            **({"max_tool_calls": self.max_tool_calls} if self.max_tool_calls is not None else {}),
            **({"max_additional_knowledge_calls": self.max_additional_knowledge_calls}
               if self.max_additional_knowledge_calls is not None else {}),
            response_format="text",
            # Always override any Knowledge entries in the project config.
            # None explicitly disables the corresponding subsystem.
            okf=_knowledge_config(self.okf, OkfConfig, "okf"),
            knowledge_vector=_knowledge_config(
                self.rag, VectorKnowledgeConfig, "rag"
            ),
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
