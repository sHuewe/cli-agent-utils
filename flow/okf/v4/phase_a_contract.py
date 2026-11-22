"""Strict read-only validator of the immutable V4 Phase-A artifact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from migrate_v3 import SCHEMA, safe_path

MAX_CONCEPT_BYTES = 2_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_phase_a(workspace: Path, root: str = "okf-v4/phase-a") -> tuple[dict, dict, Path]:
    base = safe_path(workspace, root + "/.placeholder", must_exist=False).parent
    if not base.is_dir() or base.is_symlink():
        raise ValueError(f"Phase-A directory missing/unsafe: {base}")
    marker = safe_path(workspace, root + "/phase-a.json")
    catalog_file = safe_path(workspace, root + "/catalog.json")
    marker_data = json.loads(marker.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    if (not isinstance(marker_data, dict) or marker_data.get("schema") != SCHEMA
            or marker_data.get("stage") != "A"
            or marker_data.get("status") != "completed"
            or not isinstance(catalog, dict) or catalog.get("schema") != SCHEMA):
        raise ValueError("Phase-A marker/catalog contract mismatch.")
    if marker_data.get("catalog_sha256") != digest(catalog_file.read_bytes()):
        raise ValueError("Phase-A catalog has changed since migration.")
    documents, concepts = catalog.get("documents"), catalog.get("concepts")
    if not isinstance(documents, list) or not isinstance(concepts, list) or not concepts:
        raise ValueError("Empty or invalid Phase-A catalog.")
    if (marker_data.get("document_count") != len(documents)
            or marker_data.get("concept_count") != len(concepts)):
        raise ValueError("Phase-A totals differ from catalog.")
    source_names: set[str] = set()
    doc_ids: set[str] = set()
    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError("Invalid source document.")
        doc_id, snapshot = doc.get("id"), doc.get("source_snapshot")
        if not isinstance(doc_id, str) or doc_id in doc_ids:
            raise ValueError("Duplicate/invalid doctrine ID.")
        doc_ids.add(doc_id)
        if not isinstance(snapshot, str) or not snapshot.startswith("sources/"):
            raise ValueError("Invalid source snapshot path.")
        source = safe_path(workspace, root + "/" + snapshot)
        if digest(source.read_bytes()) != doc.get("sha256"):
            raise ValueError("Phase-A source snapshot changed.")
        source_names.add(snapshot)
    concept_names: set[str] = set()
    concept_ids: set[str] = set()
    knowledge_ids: set[str] = set()
    for concept in concepts:
        if not isinstance(concept,dict):
            raise ValueError("Invalid concept record.")
        cid, path, doc_id = concept.get("id"), concept.get("path"), concept.get("document_id")
        if not isinstance(cid,str) or cid in concept_ids or doc_id not in doc_ids:
            raise ValueError("Invalid/duplicate concept ID.")
        concept_ids.add(cid)
        if not isinstance(path,str) or not path.startswith("doctrines/"+doc_id+"/") or not path.endswith(".md") or path in concept_names or Path(path).name.lower() == "index.md":
            raise ValueError(f"Invalid concept path: {path!r}")
        concept_names.add(path)
        item_ids = concept.get("knowledge_item_ids")
        knowledge_items = concept.get("knowledge_items")
        if not isinstance(item_ids, list) or not item_ids:
            raise ValueError(f"Concept lacks source Knowledge Items: {cid}")
        if (not isinstance(knowledge_items,list) or len(knowledge_items) != len(item_ids)
                or [item.get("id") if isinstance(item,dict) else None for item in knowledge_items] != item_ids):
            raise ValueError(f"Source Knowledge Item content/IDs mismatch: {cid}")
        for item in item_ids:
            if not isinstance(item,str) or item in knowledge_ids:
                raise ValueError("Duplicate/invalid Knowledge Item across Phase A.")
            knowledge_ids.add(item)
        file = safe_path(workspace, root + "/" + path)
        data = file.read_bytes()
        if len(data) > MAX_CONCEPT_BYTES or digest(data) != concept.get("sha256"):
            raise ValueError(f"Phase-A concept changed: {path}")
    if marker_data.get("knowledge_item_count") != len(knowledge_ids):
        raise ValueError("Phase-A Knowledge Item count mismatch.")
    for doc in documents:
        actual = {c["id"] for c in concepts if c["document_id"] == doc["id"]}
        if set(doc.get("concept_ids", [])) != actual:
            raise ValueError("Document concept membership mismatch.")
    actual_files = set()
    for file in base.rglob("*"):
        if file.is_symlink() or (hasattr(file,"is_junction") and file.is_junction()):
            raise ValueError(f"Symlink/junction in Phase A: {file}")
        if file.is_file():
            actual_files.add(file.relative_to(base).as_posix())
    required = concept_names | source_names | {"catalog.json", "phase-a.json"}
    if actual_files != required or set(marker_data.get("allowed_files",[])) != required:
        extras = sorted(actual_files - required)
        missing = sorted(required - actual_files)
        raise ValueError(f"Phase-A files violate strict contract: extras={extras[:8]}, missing={missing[:8]}")
    return marker_data, catalog, base
