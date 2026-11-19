"""Normalize legacy OKF concept-manifest paths without rebuilding concepts.

Dry-run by default. Only an exact configured OKF-root prefix is removable,
and only when the remaining path equals the corresponding group.json plan.
No model calls, source modifications, or deletions of checkpoints occur.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import tomllib


def _read_json(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"Refusing symlink input: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _safe_root(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("OKF root must be a string.")
    value = value.replace("\\", "/")
    if value.startswith("/") or ":" in value.split("/")[0]:
        raise ValueError("OKF root must be workspace-relative.")
    pieces = value.split("/")
    if not value or any(piece in ("", ".", "..") for piece in pieces):
        raise ValueError("Invalid OKF root.")
    return value


def plan_updates(workspace: Path, root: str) -> list[tuple[Path, bytes, bytes]]:
    """Return validated (manifest, original bytes, corrected bytes) tuples."""
    state_dir = workspace / "okf-batched" / "state-v3" / "docs"
    if not state_dir.is_dir() or state_dir.is_symlink():
        raise ValueError(f"OKF document state directory not found or unsafe: {state_dir}")
    prefix = root + "/"
    results: list[tuple[Path, bytes, bytes]] = []

    for document_dir in sorted(state_dir.iterdir()):
        if not document_dir.is_dir() or document_dir.is_symlink():
            continue
        group_path = document_dir / "group.json"
        manifests_dir = document_dir / "manifests"
        if manifests_dir.is_symlink():
            raise ValueError(f"Refusing symlink manifest directory: {manifests_dir}")
        if not manifests_dir.is_dir():
            continue
        if not group_path.is_file():
            if list(manifests_dir.glob("concept-*.json")):
                raise ValueError(f"Missing authoritative group.json for manifests: {group_path}")
            continue

        group = _read_json(group_path)
        concepts = group.get("concepts")
        if not isinstance(concepts, list):
            raise ValueError(f"Missing group.concepts: {group_path}")
        expected: dict[str, str] = {}
        for concept in concepts:
            if not isinstance(concept, dict):
                raise ValueError(f"Invalid planned concept: {group_path}")
            concept_id, canonical = concept.get("id"), concept.get("path")
            if (not isinstance(concept_id, str) or not concept_id
                    or "/" in concept_id or "\\" in concept_id or ".." in concept_id
                    or not isinstance(canonical, str)
                    or not canonical.startswith("doctrines/")
                    or canonical.startswith(prefix)):
                raise ValueError(f"Invalid planned concept identity/path: {group_path}")
            if concept_id in expected:
                raise ValueError(f"Duplicate concept ID: {group_path}")
            expected[concept_id] = canonical

        for manifest in sorted(manifests_dir.glob("concept-*.json")):
            if not manifest.is_file() or manifest.is_symlink():
                raise ValueError(f"Unsafe manifest file: {manifest}")
            concept_id = manifest.name[len("concept-"):-len(".json")]
            canonical = expected.get(concept_id)
            if canonical is None:
                raise ValueError(f"Manifest has no planned concept: {manifest}")
            original = manifest.read_bytes()
            data = _read_json(manifest)
            entries = data.get("concepts")
            if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
                raise ValueError(f"Expected exactly one manifest concept: {manifest}")
            entry = entries[0]
            actual = entry.get("path")
            if not isinstance(actual, str):
                raise ValueError(f"Missing manifest path: {manifest}")
            if actual == canonical:
                continue
            if actual != prefix + canonical:
                raise ValueError(
                    f"Unexpected manifest path in {manifest}: {actual!r}; "
                    f"expected {canonical!r} or {prefix + canonical!r}"
                )
            entry["path"] = canonical
            changed = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            results.append((manifest, original, changed))
    return results


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--okf-root", help="Override [vars].okf_root in the batched flow.")
    parser.add_argument("--apply", action="store_true", help="Back up and rewrite validated manifests.")
    args = parser.parse_args(argv)

    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"Workspace does not exist: {workspace}")

    config_path = workspace / "flow/okf/flow_okf_from_doctrine_batched/flow.toml"
    if args.okf_root is None:
        with config_path.open("rb") as stream:
            root = tomllib.load(stream)["vars"]["okf_root"]
    else:
        root = args.okf_root
    root = _safe_root(root)

    # Fully inspect the corpus before making ANY write. A mixed or unexpected
    # path convention must stop the migration rather than silently corrupt it.
    changes = plan_updates(workspace, root)
    for path, _, _ in changes:
        print(f'{"NORMALIZE" if args.apply else "WOULD NORMALIZE"} {path.relative_to(workspace)}')

    if args.apply:
        # Refuse conflicting backups before modifying any document in this
        # corpus, avoiding partial application due to an existing backup.
        for path, _, _ in changes:
            backup = path.with_name(path.name + ".bak-pre-root-normalize")
            if backup.exists() or backup.is_symlink():
                raise FileExistsError(f"Migration backup already exists: {backup}")
        for path, original, changed in changes:
            backup = path.with_name(path.name + ".bak-pre-root-normalize")
            # No overwrite of previous migration backups: do not silently
            # replace the user's only surviving original checkpoint.
            with backup.open("xb") as f:
                f.write(original)
            temp: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, prefix=".manifest-normalize-",
                    suffix=".tmp", delete=False
                ) as f:
                    temp = Path(f.name)
                    f.write(changed)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, path)
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
        print(f"Updated {len(changes)} checkpoint(s). Original bytes saved alongside as .bak-pre-root-normalize.")
    else:
        print(f"Dry run: {len(changes)} checkpoint(s) would change. Add --apply to write backups and fixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
