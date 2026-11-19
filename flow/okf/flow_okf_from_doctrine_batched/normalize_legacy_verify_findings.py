"""Normalize historical verify findings with an empty optional item_id.

Dry-run by default. Only findings[*].item_id == "" is removed, with all
other JSON data preserved. Every changed checkpoint must validate against
the current concept-verify.schema.json before *any* file is written.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator


BACKUP_SUFFIX = ".bak-pre-empty-item-id-normalize"
SCHEMA_PATH = Path("flow/okf/flow_okf_from_doctrine_batched/schemas/concept-verify.schema.json")
STATE_PATH = Path("okf-batched/state-v3/docs")


def _safe_path(workspace: Path, candidate: Path) -> None:
    root = workspace.resolve()
    path = candidate.absolute()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside workspace: {candidate}")
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        if current.is_symlink() or (
            callable(getattr(current, "is_junction", None))
            and current.is_junction()
        ):
            raise ValueError(f"Symlink or junction not allowed: {current}")
    if path.resolve(strict=False) != path:
        raise ValueError(f"Path escapes workspace: {candidate}")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)


def _schema(workspace: Path) -> Draft202012Validator:
    path = workspace / SCHEMA_PATH
    _safe_path(workspace, path)
    document = _load_json(path)
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def _normalize(document: object) -> tuple[object, int]:
    if not isinstance(document, dict):
        raise ValueError("Verify checkpoint is not a JSON object")
    findings = document.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("Verify findings is not a list")
    updated = dict(document)
    rewritten: list[object] = []
    removed = 0
    for finding in findings:
        if isinstance(finding, dict) and finding.get("item_id") == "":
            cleaned = dict(finding)
            del cleaned["item_id"]
            rewritten.append(cleaned)
            removed += 1
        else:
            rewritten.append(finding)
    if removed:
        updated["findings"] = rewritten
    return updated, removed


def plan_updates(workspace: Path) -> list[tuple[Path, bytes, bytes, int]]:
    """Preflight the full corpus; return only validated necessary edits."""
    workspace = workspace.resolve()
    state = workspace / STATE_PATH
    _safe_path(workspace, state)
    if not state.is_dir():
        raise ValueError(f"Missing state directory: {state}")
    validator = _schema(workspace)
    updates: list[tuple[Path, bytes, bytes, int]] = []
    for document_dir in sorted(state.iterdir()):
        _safe_path(workspace, document_dir)
        if not document_dir.is_dir():
            # Unrelated regular files under docs/ are not verify checkpoints.
            continue
        for checkpoint in sorted(document_dir.glob("concept-*-verify.json")):
            _safe_path(workspace, checkpoint)
            if not checkpoint.is_file():
                raise ValueError(f"Expected regular verify checkpoint: {checkpoint}")
            original = checkpoint.read_bytes()
            document = json.loads(original.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
            corrected, removed = _normalize(document)
            if not removed:
                continue
            errors = sorted(validator.iter_errors(corrected), key=lambda e: str(list(e.path)))
            if errors:
                first = errors[0]
                location = "/".join(str(part) for part in first.absolute_path) or "<root>"
                raise ValueError(
                    f"Checkpoint still violates verify schema: {checkpoint} "
                    f"at {location}: {first.message}"
                )
            updated = (json.dumps(corrected, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            updates.append((checkpoint, original, updated, removed))
    return updates


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true", help="Back up and normalize validated verify checkpoints")
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"Workspace is not a directory: {workspace}")

    updates = plan_updates(workspace)
    for path, _, _, removed in updates:
        action = "NORMALIZE" if args.apply else "WOULD NORMALIZE"
        print(f"{action} {path.relative_to(workspace)}: remove {removed} empty item_id field(s)")

    if not args.apply:
        print(f"Dry run: {len(updates)} checkpoint(s) would be changed. Add --apply to write backups and fixes.")
        return 0

    # Preflight all backups and source versions before touching anything.
    for path, original, _, _ in updates:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        _safe_path(workspace, backup)
        if backup.exists() or backup.is_symlink():
            raise FileExistsError(f"Existing normalization backup: {backup}")
        if path.read_bytes() != original:
            raise ValueError(f"Checkpoint changed during preflight: {path}")

    for path, original, updated, _ in updates:
        # Refuse replacing an input changed between preflight and writing.
        if path.read_bytes() != original:
            raise ValueError(f"Checkpoint changed during normalization: {path}")
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        with backup.open("xb") as handle:
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".verify-normalize-",
                suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    print(f"Updated {len(updates)} verify checkpoint(s); backups saved with suffix {BACKUP_SUFFIX}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
