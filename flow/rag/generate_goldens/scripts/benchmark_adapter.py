"""Minimal bridge between cli-agent SDK outputs and native DeepEval test cases.

The target agent never sees expected_output or source evidence. DeepEval owns
metric execution, caching, concurrency and reporting; this module only caches
expensive target responses and maps the optional verified Knowledge trace.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
VERSION = 3


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def load_goldens(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32_000_000:
        raise ValueError("Missing, symlinked or oversized goldens.json")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("goldens.json must be a JSON array")
    if limit is not None:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer or None")
        rows = rows[:limit]
    if not rows:
        raise ValueError("No goldens to evaluate")
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Golden must be an object")
        gid = row.get("id")
        if not isinstance(gid, str) or not CASE_ID.fullmatch(gid) or gid in ids:
            raise ValueError(f"Invalid/duplicate golden ID: {gid!r}")
        if any(not isinstance(row.get(k), str) or not row[k].strip()
               for k in ("input", "expected_output")):
            raise ValueError(f"Golden {gid} needs input and expected_output")
        ids.add(gid)
    return rows


def target_fingerprint(
    workspace: Path, config: Path | None, admin: Path | None,
    approve_tools: tuple[str, ...], capture_content: bool,
) -> str:
    """Invalidate cached target answers when relevant SDK config changes."""
    from cli_agent.settings.config import ensure_default_config_file
    from cli_agent.settings.admin_config import default_admin_config_file

    def file_hash(path: Path) -> str:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Invalid SDK config: {path}")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    project_config = (config or ensure_default_config_file()).expanduser().resolve(strict=True)
    admin_config = (admin or default_admin_config_file()).expanduser()
    local_override = workspace / ".cli-agent" / "project.toml"
    return digest({
        "version": VERSION, "workspace": str(workspace.resolve(strict=True)),
        "config": file_hash(project_config),
        "admin": file_hash(admin_config) if admin_config.is_file() else None,
        "project_override": file_hash(local_override) if local_override.is_file() else None,
        "approvals": sorted(approve_tools),
        "capture_content": capture_content, "workspace_access": "none",
    })


def deep_eval_dataset(goldens: list[dict[str, Any]]) -> Any:
    """A genuine DeepEval Golden dataset, not precomputed LLM test cases.

    evals_iterator yields these Goldens to the target *inside* a DeepEval
    evaluation run. Only the question is sent to the target's SDK Agent.
    """
    from deepeval.dataset import EvaluationDataset, Golden

    return EvaluationDataset(goldens=[
        Golden(
            input=row["input"], expected_output=row["expected_output"],
            additional_metadata={"golden_id": row["id"]},
        )
        for row in goldens
    ])


def _save_json(path: Path, value: dict[str, Any]) -> None:
    """Persist only successful target results, with atomic, private writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".response-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _response_key(golden: dict[str, Any], target_fingerprint: str) -> str:
    # Preserves compatibility with checkpoints written by the previous
    # benchmark notebook when the same target configuration is in use.
    return digest({
        "version": VERSION, "golden": golden, "target": target_fingerprint,
    })


def cached_response(
    golden: dict[str, Any], *, output: Path,
    target_fingerprint: str, fresh: bool = False,
) -> dict[str, Any] | None:
    """Optional cached target result, never a cached DeepEval score.

    Never reuse when the target fingerprint or golden has changed.
    """
    if fresh:
        return None
    path = output / "responses" / f"{golden['id']}.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict)
            or record.get("status") != "ok"
            or record.get("sha256") != _response_key(golden, target_fingerprint)
            or not isinstance(record.get("actual_output"), str)
            or not record["actual_output"].strip()):
        return None
    trace = record.get("knowledge_trace")
    if trace is not None and (
        not isinstance(trace, dict) or not isinstance(trace.get("selected"), list)
    ):
        return None
    return {
        "actual_output": record["actual_output"], "knowledge_trace": trace,
    }


def save_response(
    golden: dict[str, Any], response: dict[str, Any], *,
    output: Path, target_fingerprint: str,
) -> None:
    if (not isinstance(response, dict)
            or not isinstance(response.get("actual_output"), str)
            or not response["actual_output"].strip()):
        raise ValueError("Cannot checkpoint an empty target response")
    _save_json(
        output / "responses" / f"{golden['id']}.json",
        {
            "status": "ok", "sha256": _response_key(golden, target_fingerprint),
            "actual_output": response["actual_output"],
            "knowledge_trace": response.get("knowledge_trace"),
        },
    )


def selected_context(response: dict[str, Any]) -> list[str] | None:
    """Only host-verified selected Knowledge content; never source goldens."""
    trace = response.get("knowledge_trace")
    if not isinstance(trace, dict) or trace.get("truncated") is True:
        return None
    if trace.get("content_included") is not True:
        return None
    selected = trace.get("selected")
    if not isinstance(selected, list) or not selected:
        return None
    texts = [hit.get("content") if isinstance(hit, dict) else None for hit in selected]
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        return None
    return texts


def retrieval_test_cases(
    goldens: list[dict[str, Any]], responses: dict[str, dict[str, Any]],
) -> list[Any]:
    """Optional second native DeepEval pass for cases with observed retrieval."""
    from deepeval.test_case import LLMTestCase

    cases = []
    for golden in goldens:
        response = responses[golden["id"]]
        context = selected_context(response)
        if not context:
            continue
        cases.append(LLMTestCase(
            input=golden["input"],
            expected_output=golden["expected_output"],
            actual_output=response["actual_output"],
            retrieval_context=context,
        ))
    return cases


def judge_model(provider: str, name: str, base_url: str | None = None) -> Any:
    """A SEPARATE DeepEval judge, never the cli-agent's configured model."""
    from deepeval.models import OpenAIModel, OpenRouterModel, OllamaModel

    if not isinstance(name, str) or not name.strip():
        raise ValueError("JUDGE_MODEL must be explicitly configured")
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY required for OpenAI judge")
        return OpenAIModel(model=name, api_key=key, base_url=base_url)
    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY required for OpenRouter judge")
        params = {"model": name, "api_key": key}
        if base_url:
            params["base_url"] = base_url
        return OpenRouterModel(**params)
    if provider == "ollama":
        params = {"model": name}
        if base_url:
            params["base_url"] = base_url
        return OllamaModel(**params)
    raise ValueError("JUDGE_PROVIDER must be openai, openrouter or ollama")


def benchmark_metrics(judge: Any, threshold: float = 0.7, retrieval: bool = False) -> list[Any]:
    from deepeval.metrics import AnswerRelevancyMetric, GEval
    from deepeval.test_case import SingleTurnParams

    params = {"threshold": threshold, "model": judge}
    metrics = [
        GEval(
            name="AnswerCorrectness",
            criteria=(
                "Compare the actual answer with the expected reference. Verify all "
                "necessary facts, conditions, exceptions and multi-document "
                "dependencies. Accept paraphrases; penalize missing or invented facts."
            ),
            evaluation_params=[
                SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            **params,
        ),
        AnswerRelevancyMetric(**params),
    ]
    if retrieval:
        from deepeval.metrics import (
            FaithfulnessMetric, ContextualRecallMetric, ContextualPrecisionMetric
        )
        metrics += [
            FaithfulnessMetric(**params),
            ContextualRecallMetric(**params),
            ContextualPrecisionMetric(**params),
        ]
    return metrics


def source_recall(golden: dict[str, Any], response: dict[str, Any]) -> dict[str, float] | None:
    """Optional cli-agent-specific diagnostics, separate from judge metrics."""
    trace, sources = response.get("knowledge_trace"), golden.get("sources")
    if not isinstance(trace, dict) or trace.get("truncated") is True:
        return None
    if not isinstance(sources, list) or not sources:
        return None
    def clean(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip().replace("\\", "/").removeprefix("./").rstrip("/")
    required = {clean(s.get("path")) for s in sources if isinstance(s, dict)}
    if not required or None in required:
        return None
    searches = trace.get("searches")
    selected = trace.get("selected")
    if not isinstance(searches, list) or not isinstance(selected, list):
        return None
    initial, candidates = set(), set()
    for search in searches:
        if not isinstance(search, dict) or not isinstance(search.get("hits"), list):
            return None
        for hit in search["hits"]:
            if not isinstance(hit, dict):
                return None
            path = clean(hit.get("source"))
            if path:
                candidates.add(path)
                if search.get("stage") == "initial":
                    initial.add(path)
    final = {clean(s.get("source")) for s in selected if isinstance(s, dict)}
    return {
        "initial_recall": len(initial & required) / len(required),
        "candidate_recall": len(candidates & required) / len(required),
        "selection_recall": len(final & required) / len(required),
    }
