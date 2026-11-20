"""Repair missing or blank route identity metadata in historical scan JSON.

The scan prompt always asked for document_id, folder_id and chunk_id, but
earlier JSON Schemas did not require them. The grouping operation does.
The authoritative document slug comes from the state directory; section
IDs, source paths and line ranges come from sections.json. Nothing is
inferred from model-written candidate concepts or knowledge content.

Dry-run by default. Existing *nonempty* conflicting identities fail closed.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator


STATE_PATH = Path("okf-batched/state-v3/docs")
SCHEMA_PATH = Path(
    "flow/okf/flow_okf_from_doctrine_batched/schemas/scan.schema.json"
)
BACKUP_SUFFIX = ".bak-pre-route-ids"


def _safe_path(workspace: Path, candidate: Path) -> None:
    root = workspace.resolve()
    path = candidate.absolute()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside workspace: {candidate}")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink() or (
            callable(getattr(current, "is_junction", None))
            and current.is_junction()
        ):
            raise ValueError(f"Symlink or junction not allowed: {current}")
    if path.resolve(strict=False) != path:
        raise ValueError(f"Path resolves outside workspace: {candidate}")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_json(path: Path) -> object:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_no_duplicate_keys,
    )


def _sections(workspace: Path, directory: Path) -> tuple[str, dict[str, dict]]:
    path = directory / "sections.json"
    _safe_path(workspace, path)
    if not path.is_file():
        raise ValueError(f"Missing sections.json for scan checkpoint: {directory}")
    plan = _load_json(path)
    if not isinstance(plan, dict) or not isinstance(plan.get("source_path"), str):
        raise ValueError(f"Malformed sections.json: {path}")
    source_path = plan["source_path"]
    if not source_path.strip():
        raise ValueError(f"Missing source path in {path}")
    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(f"Missing section definitions in {path}")
    by_id: dict[str, dict] = {}
    for item in sections:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid section in {path}")
        sid = item.get("id")
        if not isinstance(sid, str) or not sid or sid in by_id:
            raise ValueError(f"Invalid or duplicate section ID in {path}: {sid!r}")
        if any(type(item.get(field)) is not int or item[field] < 1
               for field in ("start_line", "end_line")):
            raise ValueError(f"Invalid section line range in {path}: {sid}")
        by_id[sid] = item
    return source_path, by_id


def plan_updates(
    workspace: Path, *, document: str = "*",
) -> tuple[list[tuple[Path, bytes, bytes, tuple[str, ...]]], int]:
    """Preflight the selected corpus before applying any filesystem edits."""
    workspace = workspace.resolve()
    state = workspace / STATE_PATH
    _safe_path(workspace, state)
    if not state.is_dir():
        raise ValueError(f"Missing state directory: {state}")
    schema_path = workspace / SCHEMA_PATH
    _safe_path(workspace, schema_path)
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    updates = []
    scanned = 0
    matched = 0
    for directory in sorted(state.iterdir()):
        _safe_path(workspace, directory)
        if not directory.is_dir() or not fnmatchcase(directory.name, document):
            continue
        matched += 1
        checkpoints = sorted(directory.glob("scan-*.json"))
        if not checkpoints:
            continue
        source_path, sections = _sections(workspace, directory)
        for path in checkpoints:
            _safe_path(workspace, path)
            if not path.is_file():
                raise ValueError(f"Expected regular scan checkpoint: {path}")
            sid = path.name[len("scan-"):-len(".json")]
            section = sections.get(sid)
            if section is None:
                raise ValueError(f"Scan checkpoint has no planned section: {path}")
            original = path.read_bytes()
            scan = json.loads(
                original.decode("utf-8"),
                object_pairs_hook=_no_duplicate_keys,
            )
            if not isinstance(scan, dict):
                raise ValueError(f"Scan checkpoint is not a JSON object: {path}")
            expected_existing = {
                "section_id": sid,
                "source_path": source_path,
                "start_line": section["start_line"],
                "end_line": section["end_line"],
            }
            for key, value in expected_existing.items():
                if scan.get(key) != value:
                    raise ValueError(
                        f"{path}: {key}={scan.get(key)!r}, expected {value!r}"
                    )
            expected_ids = {
                "document_id": directory.name,
                "folder_id": directory.name,
                "chunk_id": sid,
            }
            updated = dict(scan)
            changed = []
            for key, value in expected_ids.items():
                current = updated.get(key)
                if current is None or (
                    isinstance(current, str) and not current.strip()
                ):
                    updated[key] = value
                    changed.append(key)
                elif current != value:
                    raise ValueError(
                        f"{path}: conflicting {key}={current!r}, expected {value!r}"
                    )
            scanned += 1
            if not changed:
                continue
            errors = sorted(
                validator.iter_errors(updated),
                key=lambda issue: str(list(issue.absolute_path)),
            )
            if errors:
                issue = errors[0]
                location = "/".join(map(str, issue.absolute_path)) or "<root>"
                raise ValueError(
                    f"{path}: scan still violates schema at {location}: "
                    f"{issue.message}"
                )
            replacement = (
                json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            updates.append((path, original, replacement, tuple(changed)))
    if not matched:
        raise ValueError(f"No document matches --document {document!r}")
    return updates, scanned


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--document", default="*",
        help="Document slug or glob pattern, e.g. '*russian-way-of-war*'",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Back up and update selected historical scan checkpoints",
    )
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"Workspace is not a directory: {workspace}")
    updates, scanned = plan_updates(workspace, document=args.document)
    for path, _, _, fields in updates:
        prefix = "UPDATE" if args.apply else "WOULD UPDATE"
        print(f"{prefix} {path.relative_to(workspace)}: {', '.join(fields)}")
    if not args.apply:
        print(
            f"Dry run: {len(updates)} of {scanned} scan checkpoints need "
            "route metadata. Add --apply to back up and update them."
        )
        return 0

    # Refuse any writes if an earlier backup exists or a source changed.
    for path, before, _, _ in updates:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        _safe_path(workspace, backup)
        _safe_path(workspace, path)
        if backup.exists() or backup.is_symlink():
            raise FileExistsError(f"Existing backup: {backup}")
        if path.read_bytes() != before:
            raise ValueError(f"Scan changed during preflight: {path}")
    for path, before, after, _ in updates:
        _safe_path(workspace, path)
        if path.read_bytes() != before:
            raise ValueError(f"Scan changed during normalization: {path}")
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        with backup.open("xb") as handle:
            handle.write(before)
            handle.flush()
            os.fsync(handle.fileno())
        tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".scan-route-normalize-",
                suffix=".tmp", mode="wb", delete=False,
            ) as handle:
                tmp = Path(handle.name)
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    print(f"Updated {len(updates)} scan checkpoints; backups: *{BACKUP_SUFFIX}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
