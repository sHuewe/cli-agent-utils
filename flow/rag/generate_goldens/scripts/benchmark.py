#!/usr/bin/env python3
"""Run generated RAG goldens with the cli-agent Python SDK and score with DeepEval.

Only golden["input"] is sent to Agent.ask(). Answers are independently
checkpointed; evaluation is a separate, restartable phase. No reference
answer or reference evidence is ever injected into the tested agent.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable

MAX_GOLDENS_BYTES = 32_000_000
MAX_CASE_BYTES = 2_000_000
MAX_CONTEXT_BYTES = 16_000_000
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
VERSION = 1


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path, *, max_bytes: int) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError(f"Missing, symlinked or oversized JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Atomically replace checkpoints; partially written JSON is never resumed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".checkpoint-",
            suffix=".tmp", delete=False,
        ) as stream:
            temp = Path(stream.name)
            os.chmod(temp, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def load_goldens(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    raw = read_json(path, max_bytes=MAX_GOLDENS_BYTES)
    if not isinstance(raw, list):
        raise ValueError("goldens.json must contain a JSON array")
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        raw = raw[:limit]
    if not raw:
        raise ValueError("No goldens to run (the generator may have found none)")
    seen = set()
    result = []
    for index, golden in enumerate(raw):
        if not isinstance(golden, dict):
            raise ValueError(f"Golden {index} is not an object")
        gid, question, expected = (
            golden.get("id"), golden.get("input"), golden.get("expected_output")
        )
        if not isinstance(gid, str) or not CASE_ID.fullmatch(gid):
            raise ValueError(f"Invalid golden id at index {index}: {gid!r}")
        if gid in seen:
            raise ValueError(f"Duplicate golden id: {gid}")
        if (not isinstance(question, str) or not question.strip()
                or len(question) > 10_000
                or not isinstance(expected, str) or not expected.strip()
                or len(expected) > 100_000):
            raise ValueError(f"Golden {gid} requires input and expected_output")
        seen.add(gid)
        result.append(golden)
    return result


def get_config_paths(config: Path | None, admin: Path | None) -> tuple[Path, Path | None]:
    # For reproducibility use a concrete SDK config path, including when the
    # caller relies on cli-agent's default config.
    if config is None:
        from cli_agent.settings.config import ensure_default_config_file
        config = ensure_default_config_file()
    config = config.expanduser().resolve(strict=True)
    if not config.is_file():
        raise ValueError("SDK project config must be a file")
    if admin is not None:
        admin = admin.expanduser().resolve(strict=True)
        if not admin.is_file():
            raise ValueError("Admin policy must be a file")
    return config, admin


def run_fingerprint(*, config: Path, admin: Path | None,
                    workspace: Path, approve_tools: tuple[str, ...]) -> str:
    # Hash real configuration files, not their contents in benchmark results.
    # Include project-local overrides and the default admin policy when used.
    if admin is None:
        from cli_agent.settings.admin_config import default_admin_config_file
        admin = default_admin_config_file()
    project_override = workspace / ".cli-agent" / "project.toml"
    return digest({
        "sdk": "cli-agent", "runner_version": VERSION,
        "workspace": str(workspace),
        "config_sha256": file_digest(config),
        "admin_sha256": file_digest(admin) if admin.is_file() else "not-present",
        "project_overrides_sha256": (
            file_digest(project_override) if project_override.is_file()
            else "not-present"
        ),
        "approval_names": sorted(approve_tools),
        "workspace_access": "none",
        "session_isolation": "fresh-agent-per-golden",
    })


def case_path(output: Path, golden_id: str) -> Path:
    return output / "responses" / f"{golden_id}.json"


def score_path(output: Path, golden_id: str) -> Path:
    return output / "scores" / f"{golden_id}.json"


def is_current(record: Any, *, golden_hash: str, runner_hash: str) -> bool:
    return (
        isinstance(record, dict) and record.get("status") == "ok"
        and record.get("golden_sha256") == golden_hash
        and record.get("runner_sha256") == runner_hash
        and isinstance(record.get("actual_output"), str)
        and bool(record["actual_output"].strip())
    )


def serialize_usage(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    return {
        key: getattr(value, key, None)
        for key in ("input_tokens", "output_tokens", "total_tokens",
                    "model_calls", "reported_calls", "unreported_calls")
    }


def build_sdk_agent(*, config: Path, admin: Path | None,
                    workspace: Path, approve_tools: tuple[str, ...]) -> Any:
    from cli_agent.sdk import AgentBuilder

    builder = AgentBuilder()
    # Explicitly use the SDK's admin policy resolution: unlike the CLI,
    # SDK policies are not loaded from the system when omitted entirely.
    builder.with_admin_config(path=admin) if admin else builder.with_admin_config()
    builder.with_project_config(
        path=config, workspace=workspace, workspace_access="none",
        response_format="text",
    )
    if approve_tools:
        allowed = frozenset(approve_tools)

        async def approve(name: str, arguments: dict) -> bool:
            # Exact tool names only, never wildcards. Configured tools remain
            # subject to the SDK's normal admin and workspace security rules.
            return name in allowed

        builder.with_approval_callback(approve)
    return builder.build()


async def ask_one(golden: dict[str, Any], *,
                  agent_factory: Callable[[], Any], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    # Create a NEW agent for every golden, ensuring separate conversation,
    # evidence, prior tool approvals, and reference contexts.
    agent = agent_factory()
    async with agent:
        result = await asyncio.wait_for(agent.ask(golden["input"]), timeout=timeout)
    answer = getattr(result, "answer", None)
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("SDK returned an empty answer")
    calls = []
    for call in getattr(result, "tool_calls", ()):
        calls.append({
            "name": str(call.name), "status": str(call.status),
            "duration_ms": getattr(call, "duration_ms", None),
        })
    return {
        "actual_output": answer,
        "duration_seconds": round(time.monotonic() - started, 3),
        "tool_calls": calls,
        "usage": serialize_usage(getattr(result, "usage", None)),
    }


async def run_cases(
    goldens: list[dict[str, Any]], *, output: Path, runner_sha: str,
    agent_factory: Callable[[], Any], timeout: float, fresh: bool,
) -> dict[str, int]:
    summary = {"completed": 0, "reused": 0, "failed": 0}
    for pos, golden in enumerate(goldens, 1):
        gid, gh = golden["id"], digest(golden)
        path = case_path(output, gid)
        if path.exists() and not fresh:
            old = read_json(path, max_bytes=MAX_CASE_BYTES)
            if is_current(old, golden_hash=gh, runner_hash=runner_sha):
                summary["reused"] += 1
                print(f"[{pos}/{len(goldens)}] reuse {gid}", flush=True)
                continue
        print(f"[{pos}/{len(goldens)}] SDK {gid}", flush=True)
        try:
            answer = await ask_one(golden, agent_factory=agent_factory,
                                   timeout=timeout)
            record = {
                "version": VERSION, "id": gid, "status": "ok",
                "golden_sha256": gh, "runner_sha256": runner_sha,
                **answer,
            }
            summary["completed"] += 1
        except Exception as exc:
            # No sensitive exception messages (which can include model URLs,
            # server error payloads or credentials) are persisted by default.
            record = {
                "version": VERSION, "id": gid, "status": "error",
                "golden_sha256": gh, "runner_sha256": runner_sha,
                "error_type": type(exc).__name__,
            }
            summary["failed"] += 1
            print(f"  failed: {type(exc).__name__}", flush=True)
        write_json(path, record)
    return summary


def validate_actual_contexts(path: Path | None) -> dict[str, dict[str, Any]]:
    """Optional contexts observed by the ACTUAL retriever, never golden quotes.

    Contract: {"id": {"runner_sha256": "<agent run>", "chunks": ["..."]}}.
    A matching run fingerprint is required to prevent stale provenance.
    """
    if path is None:
        return {}
    raw = read_json(path, max_bytes=MAX_CONTEXT_BYTES)
    if not isinstance(raw, dict):
        raise ValueError("retrieval contexts must be a JSON object keyed by golden ID")
    for gid, value in raw.items():
        if (not isinstance(gid, str) or not CASE_ID.fullmatch(gid)
                or not isinstance(value, dict)):
            raise ValueError("Invalid retrieval context entry")
        chunks = value.get("chunks")
        if (not isinstance(value.get("runner_sha256"), str)
                or not isinstance(chunks, list) or len(chunks) > 30
                or any(not isinstance(x, str) or not x.strip()
                       or len(x) > 15000 for x in chunks)):
            raise ValueError(f"Invalid observed chunks for {gid}")
    return raw


def create_metrics(*, threshold: float, model: str | None,
                   has_retrieval: bool) -> list[Any]:
    # Import lazily so the SDK run phase does not require DeepEval.
    from deepeval.metrics import GEval, AnswerRelevancyMetric
    from deepeval.test_case import SingleTurnParams

    kw = {"threshold": threshold, "async_mode": False}
    if model is not None:
        kw["model"] = model
    metrics: list[Any] = [
        GEval(
            name="AnswerCorrectness",
            criteria=(
                "Evaluate whether ACTUAL_OUTPUT gives a factually accurate and "
                "sufficiently complete answer to INPUT relative to EXPECTED_OUTPUT. "
                "Preserve logical qualifiers, prerequisites, exceptions and links "
                "between multiple documents. Heavily penalize omitted required "
                "facts, contradictions, unsupported specificity, or refusal when "
                "the reference has a clear answer. Accept semantically equivalent "
                "wording without requiring verbatim reproduction."
            ),
            evaluation_params=[
                SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            **kw,
        ),
        AnswerRelevancyMetric(**kw),
    ]
    if has_retrieval:
        from deepeval.metrics import (
            FaithfulnessMetric, ContextualRecallMetric, ContextualPrecisionMetric,
        )
        metrics.extend([
            FaithfulnessMetric(**kw),
            ContextualRecallMetric(**kw),
            ContextualPrecisionMetric(**kw),
        ])
    return metrics


def evaluate_cases(
    goldens: list[dict[str, Any]], *, output: Path, runner_sha: str,
    threshold: float, judge_model: str | None, fresh: bool,
    retrieval_contexts: dict[str, dict[str, Any]] | None = None,
    metrics_factory: Callable[..., list[Any]] = create_metrics,
    testcase_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if testcase_factory is None:
        from deepeval.test_case import LLMTestCase
        testcase_factory = LLMTestCase

    contexts = retrieval_contexts or {}
    summary: dict[str, Any] = {
        "evaluated": 0, "reused": 0, "skipped": 0, "errors": 0,
        "passed": 0, "failed": 0, "scores": {},
    }
    for pos, golden in enumerate(goldens, 1):
        gid, gh = golden["id"], digest(golden)
        response_file = case_path(output, gid)
        if not response_file.exists():
            summary["skipped"] += 1
            continue
        response = read_json(response_file, max_bytes=MAX_CASE_BYTES)
        if not is_current(response, golden_hash=gh, runner_hash=runner_sha):
            summary["skipped"] += 1
            continue

        observed = contexts.get(gid)
        chunks = None
        if observed is not None:
            if observed["runner_sha256"] != runner_sha:
                raise ValueError(f"Stale retrieval contexts for {gid}")
            chunks = observed["chunks"]
        # Distinguish "not observed" from "retriever returned zero chunks".
        # An observed empty context is intentionally not sent to metrics that
        # require a nonempty grounding context; mark it explicitly.
        has_context = bool(chunks)
        eval_sha = digest({
            "golden_sha256": gh,
            "response_sha256": digest(response),
            "judge_model": judge_model or "deepeval-default",
            "threshold": threshold,
            "retrieval_sha256": digest(chunks) if observed is not None else None,
            "metric_version": VERSION,
        })
        out = score_path(output, gid)
        if out.exists() and not fresh:
            old = read_json(out, max_bytes=MAX_CASE_BYTES)
            if old.get("evaluation_sha256") == eval_sha and old.get("status") == "ok":
                summary["reused"] += 1
                _count_score(summary, old)
                continue

        print(f"[{pos}/{len(goldens)}] DeepEval {gid}", flush=True)
        try:
            test_case = testcase_factory(
                input=golden["input"],
                expected_output=golden["expected_output"],
                actual_output=response["actual_output"],
                **({"retrieval_context": chunks} if has_context else {}),
            )
            results = {}
            for metric in metrics_factory(
                threshold=threshold, model=judge_model,
                has_retrieval=has_context,
            ):
                metric.measure(test_case)
                score = getattr(metric, "score", None)
                if (isinstance(score, bool) or not isinstance(score, (int, float))
                        or not math.isfinite(score)):
                    raise ValueError(f"Invalid DeepEval score for {metric.__class__.__name__}")
                name = str(getattr(metric, "name", None) or metric.__class__.__name__)
                if name in results:
                    raise ValueError(f"Duplicate DeepEval metric: {name}")
                results[name] = {
                    "score": float(score),
                    "threshold": threshold,
                    "passed": bool(metric.is_successful()),
                    "reason": str(getattr(metric, "reason", "") or "")[:4000],
                }
            record = {
                "version": VERSION, "id": gid, "status": "ok",
                "evaluation_sha256": eval_sha,
                "overall_passed": all(m["passed"] for m in results.values()),
                "retrieval_observed": observed is not None,
                "retrieval_context_count": len(chunks) if chunks is not None else None,
                "metrics": results,
            }
            summary["evaluated"] += 1
        except Exception as exc:
            record = {
                "version": VERSION, "id": gid, "status": "error",
                "evaluation_sha256": eval_sha,
                "error_type": type(exc).__name__,
            }
            summary["errors"] += 1
            print(f"  failed: {type(exc).__name__}", flush=True)
        write_json(out, record)
        _count_score(summary, record)

    # Avoid treating failed/missing SDK cases as a successful 100% benchmark.
    summary["total"] = len(goldens)
    summary["complete"] = (
        summary["skipped"] == 0 and summary["errors"] == 0
        and summary["evaluated"] + summary["reused"] == len(goldens)
    )
    summary["scores"] = {
        name: {"mean": round(values["sum"] / values["count"], 4),
               "count": values["count"]}
        for name, values in sorted(summary["scores"].items())
    }
    write_json(output / "summary.json", summary)
    return summary


def _count_score(summary: dict[str, Any], record: dict[str, Any]) -> None:
    if record.get("status") != "ok":
        return
    key = "passed" if record.get("overall_passed") else "failed"
    summary[key] += 1
    for name, value in record.get("metrics", {}).items():
        agg = summary["scores"].setdefault(name, {"sum": 0.0, "count": 0})
        agg["sum"] += value["score"]
        agg["count"] += 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["run", "evaluate", "all"], default="all")
    parser.add_argument("--goldens", type=Path, default=Path("rag-goldens/goldens.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("rag-goldens/evaluation"))
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, help="cli-agent project config.toml (default: user config)")
    parser.add_argument("--admin-config", type=Path, help="admin policy TOML (default: system policy)")
    parser.add_argument("--approve-tool", action="append", default=[],
                        metavar="EXACT_TOOL", help="Preapprove exact SDK tool name for this run")
    parser.add_argument("--timeout", type=float, default=600,
                        help="Per-question SDK timeout in seconds (default: 600)")
    parser.add_argument("--limit", type=int, help="Only first N goldens (smoke test)")
    parser.add_argument("--fresh", action="store_true",
                        help="Rerun even when a compatible checkpoint exists")
    parser.add_argument("--judge-model", help="DeepEval judge model (default: DeepEval default)")
    parser.add_argument("--threshold", type=float, default=0.7,
                        help="DeepEval pass threshold, 0..1")
    parser.add_argument("--retrieval-context-file", type=Path,
                        help="Optional observed RAG chunks; must match run fingerprint")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >=1")
    if len(set(args.approve_tool)) != len(args.approve_tool) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+__[A-Za-z0-9_-]+", name)
        for name in args.approve_tool
    ):
        parser.error("--approve-tool requires distinct exact server__tool names")
    if args.phase == "run" and args.retrieval_context_file:
        parser.error("--retrieval-context-file applies to evaluation only")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = args.workspace.expanduser().resolve(strict=True)
    output = args.output_dir.expanduser().resolve(strict=False)
    goldens = load_goldens(args.goldens, limit=args.limit)
    config, admin = get_config_paths(args.config, args.admin_config)
    runner_sha = run_fingerprint(
        config=config, admin=admin, workspace=workspace,
        approve_tools=tuple(args.approve_tool),
    )
    print(f"Loaded {len(goldens)} goldens; runner_sha256={runner_sha}", flush=True)
    run_summary: dict[str, Any] | None = None
    if args.phase in {"run", "all"}:
        run_summary = asyncio.run(run_cases(
            goldens, output=output, runner_sha=runner_sha,
            agent_factory=lambda: build_sdk_agent(
                config=config, admin=admin, workspace=workspace,
                approve_tools=tuple(args.approve_tool),
            ),
            timeout=args.timeout, fresh=args.fresh,
        ))
        print("SDK:", json.dumps(run_summary), flush=True)
    if args.phase == "run":
        return 1 if run_summary and run_summary["failed"] else 0

    contexts = validate_actual_contexts(args.retrieval_context_file)
    result = evaluate_cases(
        goldens, output=output, runner_sha=runner_sha,
        threshold=args.threshold, judge_model=args.judge_model,
        fresh=args.fresh, retrieval_contexts=contexts,
    )
    print("DeepEval:", json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
