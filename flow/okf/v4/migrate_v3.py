"""One-time, checkpoint-preserving V3 -> V4 Phase-A migration.

Phase A contains ONLY doctrine concepts, their source snapshots and a
machine-readable catalog/completion marker. Indexes, themes, manifests and
legacy checkpoints are never copied. Dry-run is the default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import posixpath
import re
import shutil
import tempfile
import unicodedata

SCHEMA = "okf.phase-a.v1"
RESERVED = {"index", "con", "prn", "aux", "nul", *{f"com{i}" for i in range(1, 10)}, *{f"lpt{i}" for i in range(1, 10)}}


def safe_path(workspace: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Unsafe workspace path: {relative!r}")
    parts = relative.split("/")
    windows = PureWindowsPath(relative)
    if (windows.drive or windows.is_absolute() or relative.startswith("/")
            or any(part in ("", ".", "..") for part in parts)):
        raise ValueError(f"Unsafe workspace path: {relative!r}")
    current = workspace
    for part in parts:
        current /= part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"Symlink/junction refused: {current}")
    if must_exist and not current.is_file():
        raise ValueError(f"Required file missing: {current}")
    return current


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required JSON missing or unsafe: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def slugify(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Concept title missing.")
    translit = {"Ä":"Ae","Ö":"Oe","Ü":"Ue","ä":"ae","ö":"oe","ü":"ue","ß":"ss"}
    text = "".join(translit.get(c,c) for c in title)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:72].rstrip("-")
    if not text or text in RESERVED:
        raise ValueError(f"Unusable concept title: {title!r}")
    return text


def theme_slug(label: str) -> str:
    """Produce a deterministic, publication-safe slug for any valid theme.

    Theme labels are not concept filenames: names such as "Index", "CON",
    and non-Latin script are legitimate LLM labels. Keep the existing
    human-readable slug for ordinary tags, but use a disjoint namespace
    (double hyphen, impossible from slugify) for reserved and otherwise
    unrepresentable names. This also prevents collisions with other ordinary
    theme slugs and with the mandatory themen/index.md overview.
    """
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Theme label must be a nonempty string.")
    try:
        return slugify(label.strip())
    except ValueError:
        normalized = unicodedata.normalize("NFKD", label.strip())
        ascii_name = normalized.encode("ascii", "ignore").decode().lower()
        stem = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:72].rstrip("-")
        if stem in RESERVED:
            return "tag--" + stem
        if not stem:
            # Same canonical Unicode label => same name; no platform-dependent
            # filename characters, and never conflicts with a normal slug.
            canonical = unicodedata.normalize("NFKC", label.strip()).casefold()
            return "tag--u-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        raise


def title_from_frontmatter(raw: str) -> str | None:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:101]:
        if line.strip() == "---":
            return None
        m = re.fullmatch(r"title:\s*(.+?)\s*", line)
        if m:
            value = m.group(1)
            if value.startswith('"') and value.endswith('"'):
                try:
                    value = json.loads(value)
                except ValueError:
                    return None
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            elif value.startswith(("[", "{", "|", ">", "!", "*", "&")):
                return None
            return value.strip() if isinstance(value, str) and value.strip() else None
    return None


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_parent(path: str, document_slug: str) -> None:
    parts = path.split("/")
    if (len(parts) not in (3, 4) or parts[0:2] != ["doctrines", document_slug]
            or not parts[-1].endswith(".md") or parts[-1].casefold() == "index.md"):
        raise ValueError(f"Unexpected doctrine concept path: {path!r}")
    if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", x) for x in parts[1:-1]):
        raise ValueError(f"Invalid doctrine/semantic folder: {path!r}")


def validate_evidence(
    ranges: object, *, source_path: str, line_count: int, context: str,
) -> None:
    """Require source-bound line evidence for each imported Knowledge Item."""
    if not isinstance(ranges, list) or not ranges:
        raise ValueError(f"Missing source evidence for {context}")
    for entry in ranges:
        if not isinstance(entry, dict):
            raise ValueError(f"Malformed source evidence for {context}")
        declared = [entry[k] for k in ("doctrine", "source_path") if k in entry]
        if not declared or any(value != source_path for value in declared):
            raise ValueError(f"Evidence references a different source for {context}")
        start,end=entry.get("start_line"),entry.get("end_line")
        if (type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= line_count):
            raise ValueError(f"Evidence range outside the source for {context}")


def inspect_legacy_repair(repair: dict, *, cid: str, old: str,
                          source_root: str, item_ids: list[str]) -> dict:
    """Treat V3 LLM repair reports as diagnostics, not source authority.

    Only the original section scan and grouped source Knowledge Items are
    authoritative. A stale or incorrect LLM repair checkpoint must trigger
    B-source review, never discard an otherwise valid doctrine concept or
    invent source-item coverage.
    """
    issues = []
    if not repair:
        return {"status": "missing", "issues": ["report_missing"]}
    if repair.get("concept_id") != cid:
        issues.append("concept_id_mismatch")
    if repair.get("path") not in (old, source_root + "/" + old):
        issues.append("path_mismatch")
    if repair.get("status") not in ("ok", "repaired"):
        issues.append("status_incomplete")
    documented = repair.get("documented_item_ids")
    if (not isinstance(documented, list)
            or any(not isinstance(item, str) for item in documented)
            or len(documented) != len(set(documented))):
        issues.append("documented_ids_invalid")
    elif set(documented) != set(item_ids):
        issues.append("documented_ids_mismatch")
    remaining = repair.get("remaining_item_ids", [])
    if not isinstance(remaining, list) or remaining:
        issues.append("remaining_item_findings")
    warnings = repair.get("remaining_warnings", [])
    if not isinstance(warnings, list) or warnings:
        issues.append("remaining_warnings")
    return {
        "status": repair.get("status") if isinstance(repair.get("status"), str) else "invalid",
        "issues": issues,
    }


def _same_legacy_document_slug(actual: object, expected: str) -> bool:
    """Allow a historical truncation variant only for one hashed source.

    Some V3 scan LLM outputs used a shorter human-readable source slug than
    the directory produced by stable_slugs. Accept only a whole-token prefix
    variant with the SAME 16-hex source digest. Unrelated document IDs,
    different hashes and arbitrary aliases still fail closed.
    """
    if not isinstance(actual, str):
        return False
    pattern = r"([a-z0-9]+(?:-[a-z0-9]+)*)-([0-9a-f]{16})"
    older = re.fullmatch(pattern, actual)
    canonical = re.fullmatch(pattern, expected)
    if not older or not canonical or older.group(2) != canonical.group(2):
        return False
    first, second = older.group(1), canonical.group(1)
    short, long = sorted((first, second), key=len)
    return (
        len(short) >= 24
        and 0 < len(long) - len(short) <= 32
        and long.startswith(short + "-")
    )


def authoritative_scanned_items(
    workspace: Path, state_root: str, slug: str, sections: dict,
    source_path: str, line_count: int,
) -> tuple[dict[str, dict], list[dict]]:
    """Reconcile Phase-A coverage against ALL original V3 scan outputs.

    The V3 grouping operation prefixes each scan-local item ID with its
    document ID and otherwise preserves the original item fields verbatim.
    Group/coverage alone cannot certify that extraction was complete.
    """
    planned = sections.get("sections")
    if not isinstance(planned, list) or not planned:
        raise ValueError(f"No authoritative V3 scan sections for {slug}")
    scanned: dict[str, dict] = {}
    route_aliases: list[dict] = []
    section_ids: set[str] = set()
    for section in planned:
        if not isinstance(section, dict):
            raise ValueError(f"Invalid section plan for {slug}")
        sid = section.get("id")
        start, end = section.get("start_line"), section.get("end_line")
        if (not isinstance(sid, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]+", sid)
                or sid in section_ids
                or type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= line_count):
            raise ValueError(f"Invalid V3 section ID/range in {slug}")
        section_ids.add(sid)
        scan_path = f"{state_root}/{slug}/scan-{sid}.json"
        scan = read_json(safe_path(workspace, scan_path))
        # Earlier V3 schemas allowed missing/blank routing IDs even though
        # sections.json and the state directory uniquely determine them.
        # Accept omissions *in memory*. Explicitly populated document
        # identities are accepted only for a hash-identical historical
        # source slug prefix variant, recorded for provenance.
        required = {
            "status": "ok", "source_path": source_path,
            "section_id": sid, "start_line": start, "end_line": end,
        }
        for field, expected in required.items():
            if scan.get(field) != expected or (
                    field in ("start_line", "end_line")
                    and type(scan.get(field)) is not int):
                raise ValueError(
                    f"V3 scan section mismatch {slug}/{sid}: "
                    f"{field}={scan.get(field)!r}, expected {expected!r}"
                )
        for field, expected in (
            ("chunk_id", sid), ("document_id", slug), ("folder_id", slug),
        ):
            actual = scan.get(field)
            if actual is None or (isinstance(actual, str) and not actual.strip()):
                continue
            if actual != expected:
                if (field in ("document_id", "folder_id")
                        and _same_legacy_document_slug(actual, expected)):
                    route_aliases.append({
                        "section_id": sid, "field": field,
                        "legacy": actual, "canonical": expected,
                    })
                else:
                    raise ValueError(
                        f"V3 scan routing conflict {slug}/{sid}: "
                        f"{field}={actual!r}, expected {expected!r}"
                    )
        items = scan.get("knowledge_items")
        if not isinstance(items, list):
            raise ValueError(f"Scan Knowledge Items missing in {slug}/{sid}")
        for entry in items:
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid scanned Knowledge Item in {slug}/{sid}")
            local_id = entry.get("id")
            if not isinstance(local_id, str) or not local_id:
                raise ValueError(f"Invalid scanned item ID in {slug}/{sid}")
            qualified = f"{slug}:{local_id}"
            if qualified in scanned:
                raise ValueError(f"Duplicate scan Knowledge Item ID: {qualified}")
            validate_evidence(
                entry.get("evidence_ranges"), source_path=source_path,
                line_count=line_count, context=f"scan {slug}/{sid}/{local_id}",
            )
            if any(
                ev["start_line"] < start or ev["end_line"] > end
                for ev in entry["evidence_ranges"]
            ):
                raise ValueError(f"Scanned item evidence outside section: {qualified}")
            scanned[qualified] = {**entry, "id": qualified}
    if not scanned:
        raise ValueError(f"No Knowledge Items found in V3 source scans: {slug}")
    return scanned, route_aliases


def _markdown_links(body: str, old: str, new: str, mapping: dict[str, str],
                    *, allow_deferred_index_links: bool = False) -> str:
    """Rewrite concept links; defer legacy index links only in Phase A.

    Phase A excludes old index.md files and Phase C generates new ones.
    With allow_deferred_index_links, retain a reference to an index that
    does not yet exist; Phase C calls this helper without that flag and
    validates such references against generated navigation pages.
    Unexpected internal Markdown links remain errors.
    """
    from urllib.parse import unquote, quote, urlsplit
    pattern = re.compile(r"(?P<before>\]\(\s*|\[[^\]\n]+\]:[ \t]*)(?P<url><[^>\n]+>|[^\s()]+)", re.M)
    codes = re.compile(r"(?<!\x60)(?P<t>\x60+)(?!\x60).*?(?<!\x60)(?P=t)(?!\x60)", re.S)
    fences = re.compile(r"^[ ]{0,3}(\x60{3,}|~{3,})(.*)$")
    def rewrite(segment: str) -> str:
        def transform(match: re.Match) -> str:
            value = match["url"]
            enclosed = value.startswith("<") and value.endswith(">")
            target = value[1:-1] if enclosed else value
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
                return match.group()
            decoded = unquote(parsed.path)
            original = posixpath.normpath(posixpath.join(posixpath.dirname(old), decoded))
            # Navigation indexes are regenerated in C, never imported into A.
            # Canonicalize case-insensitive historical index references at
            # publication so that the link works on case-sensitive systems.
            mapped = original
            if posixpath.basename(original).casefold() == "index.md":
                canonical = posixpath.join(posixpath.dirname(original), "index.md")
                if canonical in mapping:
                    mapped = canonical
            if mapped in mapping:
                relative = posixpath.relpath(mapping[mapped], posixpath.dirname(new))
                fixed = quote(relative, safe="/-._~")
                if parsed.query:
                    fixed += "?" + parsed.query
                if parsed.fragment:
                    fixed += "#" + parsed.fragment
                return match["before"] + ("<"+fixed+">" if enclosed else fixed)
            if (allow_deferred_index_links
                    and posixpath.basename(original).casefold() == "index.md"):
                return match.group()
            if decoded.lower().endswith(".md"):
                raise ValueError(f"Unresolved concept Markdown link in {old}: {target!r}")
            return match.group()
        result = []
        prev = 0
        for m in codes.finditer(segment):
            result.append(pattern.sub(transform, segment[prev:m.start()]))
            result.append(m.group())
            prev = m.end()
        result.append(pattern.sub(transform, segment[prev:]))
        return "".join(result)
    lines = body.splitlines(keepends=True)
    chunk, result = [], []
    fenced = None
    for line in lines:
        m = fences.match(line.rstrip("\r\n"))
        marker, tail = (m.group(1),m.group(2)) if m else (None,None)
        valid_open = marker and (marker[0] == "~" or "\x60" not in tail)
        if fenced is None and valid_open:
            result.append(rewrite("".join(chunk)))
            chunk = []
            fenced = (marker[0],len(marker))
            result.append(line)
        elif fenced:
            result.append(line)
            if marker and marker[0] == fenced[0] and len(marker) >= fenced[1] and not tail.strip():
                fenced = None
        else:
            chunk.append(line)
    result.append(rewrite("".join(chunk)))
    return "".join(result)


def prepare(workspace: Path, *, source_root: str, state_root: str,
            document_root: str = "doctrines") -> tuple[dict, dict[str, bytes]]:
    # Source documents live independently of generated V3 concepts, which
    # intentionally retain their doctrines/<slug>/... hierarchy.
    document_dir = safe_path(workspace, document_root+"/.placeholder", must_exist=False).parent
    generated = safe_path(workspace, source_root+"/.placeholder", must_exist=False).parent
    state = safe_path(workspace, state_root+"/.placeholder", must_exist=False).parent
    if not generated.is_dir() or not state.is_dir():
        raise ValueError("V3 generated root or state directory missing.")
    groups = sorted(p for p in state.iterdir() if p.is_dir())
    if not groups:
        raise ValueError("No V3 doctrine state directories.")
    documents, concepts, outputs = [], [], {}
    paths, ids, ki_ids = set(), set(), set()
    original_paths: dict[str,str] = {}
    pending: list[tuple[str,str,str,bytes]] = []
    for doc_dir in groups:
        if doc_dir.is_symlink() or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", doc_dir.name):
            raise ValueError(f"Unsafe document state directory: {doc_dir}")
        slug = doc_dir.name
        group_path, cover_path, section_path = (doc_dir / n for n in ("group.json","coverage.json","sections.json"))
        if not group_path.is_file() or not cover_path.is_file() or not section_path.is_file():
            raise ValueError(f"Incomplete V3 document: {slug}")
        group, cover, sections = (read_json(p) for p in (group_path,cover_path,section_path))
        # Preserve incomplete V3 coverage so B can repair it from original scans.
        if cover.get("status") != "ok" and not (cover.get("missing_item_ids") or cover.get("warnings")):
            raise ValueError(f"Unexplained V3 coverage status: {slug}")
        source_path = sections.get("source_path")
        if (not isinstance(source_path, str)
                or not source_path.startswith(document_root + "/")
                or not source_path.lower().endswith((".md", ".markdown"))):
            raise ValueError(f"Unexpected source document path for {slug}: {source_path!r}")
        source = safe_path(workspace, source_path)
        source_bytes = source.read_bytes()
        source_line_count = len(source_bytes.decode("utf-8").splitlines())
        if source_line_count < 1:
            raise ValueError(f"Empty source document: {source_path}")
        scanned_items, route_aliases = authoritative_scanned_items(
            workspace, state_root, slug, sections, source_path, source_line_count,
        )
        source_item_ids = set(scanned_items)
        src_output = f"sources/{slug}{source.suffix.lower()}"
        if src_output in outputs:
            raise ValueError("Duplicate source output")
        outputs[src_output] = source_bytes
        planned = group.get("concepts")
        if (not isinstance(planned,list) or not planned
                or group.get("folder",{}).get("id") != slug
                or group.get("folder",{}).get("path") != f"doctrines/{slug}"):
            raise ValueError(f"Invalid group or empty concepts: {slug}")
        listed_items = set()
        for concept in planned:
            cid, old, title = concept.get("id"), concept.get("path"), concept.get("title")
            if not all(isinstance(x,str) and x for x in (cid,old,title)):
                raise ValueError(f"Incomplete planned concept: {slug}")
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", cid):
                raise ValueError(f"Invalid concept identifier: {cid!r}")
            assert_parent(old,slug)
            qualified_id = f"{slug}:{cid}"
            if qualified_id in ids or old in original_paths:
                raise ValueError(f"Duplicate concept ID or path: {qualified_id}")
            ids.add(qualified_id)
            old_file = safe_path(workspace,source_root+"/"+old)
            raw_bytes = old_file.read_bytes()
            raw = raw_bytes.decode("utf-8")
            final_title = title_from_frontmatter(raw) or title
            target_folder = posixpath.dirname(old)
            stem = slugify(final_title)
            target = target_folder+"/"+stem+".md"
            if target.casefold() in paths:
                suffix = re.sub(r"[^a-z0-9-]+","-",cid.lower()).strip("-")[:24]
                target = target_folder+"/"+stem[:52].rstrip("-")+"-"+suffix+".md"
            if target.casefold() in paths or target.endswith("/index.md"):
                raise ValueError(f"Unresolvable concept filename collision: {target}")
            paths.add(target.casefold())
            original_paths[old] = target
            items = concept.get("coverage_items")
            if not isinstance(items,list) or not items:
                raise ValueError(f"Concept has no source Knowledge Items: {cid}")
            item_ids = []
            for item in items:
                kid = item.get("id") if isinstance(item,dict) else None
                if not isinstance(kid,str) or not kid or kid in ki_ids:
                    raise ValueError(f"Duplicate/invalid Knowledge Item ID: {kid}")
                validate_evidence(
                    item.get("evidence_ranges"), source_path=source_path,
                    line_count=source_line_count, context=f"{cid}/{kid}",
                )
                ki_ids.add(kid); listed_items.add(kid); item_ids.append(kid)
            if concept.get("evidence_ranges"):
                validate_evidence(
                    concept["evidence_ranges"], source_path=source_path,
                    line_count=source_line_count, context=f"concept {cid}",
                )
            repair_file = doc_dir / f"concept-{cid}-repair.json"
            repair = read_json(repair_file) if repair_file.is_file() else {}
            repair_diagnostics = inspect_legacy_repair(
                repair, cid=cid, old=old, source_root=source_root, item_ids=item_ids,
            )
            repair_required = (
                bool(repair_diagnostics["issues"])
                or bool(cover.get("warnings"))
                or bool(set(cover.get("missing_item_ids", [])) & set(item_ids))
            )
            pending.append((old,target,cid,raw_bytes))
            concepts.append({
                "id": f"{slug}:{cid}", "legacy_id":cid, "document_id":slug,
                "title":final_title, "description":concept.get("description",""),
                "type":concept.get("type",""), "tags":concept.get("tags",[]),
                "related":concept.get("related",[]),
                "path":target,"source_path":src_output,
                "source_original_path":source_path,
                "knowledge_item_ids":item_ids,
                # Preserve content, types and source evidence for future
                # incremental impact analysis; these are source-grounded
                # records from group.json, not LLM-generated summaries.
                "knowledge_items":items,
                "evidence_ranges":concept.get("evidence_ranges",[]),
                "source_repair_required": repair_required,
                "legacy_repair_diagnostics": repair_diagnostics,
                "sha256":None,
            })
        # Reconcile both identities and full source-derived payloads.
        # A stale group and its derived coverage.json may agree with each
        # other while silently omitting scanned knowledge.
        grouped_items = {
            ki["id"]:ki for concept in planned
            for ki in concept["coverage_items"]
        }
        # Missing scanned items are recovered in B; modified/extra items fail.
        if (listed_items - source_item_ids
                or any(scanned_items[i] != grouped_items[i] for i in listed_items)):
            raise ValueError(
                f"Group/scan Knowledge Item mismatch for {slug}: "
                f"missing={sorted(set(scanned_items)-listed_items)[:6]}, "
                f"unexpected={sorted(listed_items-set(scanned_items))[:6]}, "
                f"modified={sorted(ident for ident in set(scanned_items)&listed_items if scanned_items[ident] != grouped_items[ident])[:6]}"
            )
        total = group.get("total_items")
        if total != len(listed_items):
            raise ValueError(f"Group item count mismatch: {slug}")
        missing = sorted(source_item_ids - listed_items)
        declared_missing = cover.get("missing_item_ids", [])
        warnings = cover.get("warnings", [])
        if (not isinstance(declared_missing, list)
                or not all(isinstance(x, str) for x in declared_missing)
                or not isinstance(warnings, list)
                or not all(isinstance(x, str) for x in warnings)
                or any(x not in source_item_ids for x in declared_missing)):
            raise ValueError(f"Malformed V3 coverage findings: {slug}")
        documents.append({
            "id":slug,"source_snapshot":src_output,
            "original_path":source_path,"sha256":checksum(source_bytes),
            "concept_ids":[x["id"] for x in concepts if x["document_id"]==slug],
            "source_knowledge_items": [scanned_items[i] for i in sorted(scanned_items)],
            "pending_knowledge_item_ids": missing,
            "legacy_scan_route_aliases": route_aliases,
            "coverage_diagnostics": {
                "status": cover.get("status"), "missing_item_ids": declared_missing,
                "warnings": warnings,
                "source_item_count": len(scanned_items),
                "grouped_item_count": len(listed_items),
            },
        })
    by_path = {x["path"]:x for x in concepts}
    for old, target, cid, data in pending:
        fixed = _markdown_links(
            data.decode("utf-8"), old, target, original_paths,
            allow_deferred_index_links=True,
        ).encode("utf-8")
        outputs[target] = fixed
        by_path[target]["sha256"] = checksum(fixed)
    catalog={"schema":SCHEMA,"documents":documents,"concepts":concepts}
    outputs["catalog.json"] = (json.dumps(catalog,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    contract={
        "schema":SCHEMA, "stage":"A","status":"completed","origin":"v3_migration",
        "catalog":"catalog.json","concept_count":len(concepts),
        "document_count":len(documents),"knowledge_item_count":len(ki_ids),
        "source_knowledge_item_count":sum(len(d["source_knowledge_items"]) for d in documents),
        "pending_knowledge_item_count":sum(len(d["pending_knowledge_item_ids"]) for d in documents),
        "catalog_sha256":checksum(outputs["catalog.json"]),
        "allowed_files":sorted([*outputs,"phase-a.json"]),
    }
    outputs["phase-a.json"] = (json.dumps(contract,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    return contract,outputs


def migrate(workspace: Path, *, source_root: str, state_root: str,
            destination: str, apply: bool = False,
            document_root: str = "doctrines") -> dict:
    workspace=workspace.resolve()
    target=safe_path(workspace,destination+"/.placeholder",must_exist=False).parent
    if any(target == parent or target in parent.parents or parent in target.parents for parent in (
        safe_path(workspace,source_root+"/.placeholder",must_exist=False).parent,
        safe_path(workspace,state_root+"/.placeholder",must_exist=False).parent,
        safe_path(workspace,document_root+"/.placeholder",must_exist=False).parent,
    )):
        raise ValueError("Phase A destination overlaps V3 sources/state/source documents.")
    contract,outputs=prepare(workspace,source_root=source_root,state_root=state_root,
                             document_root=document_root)
    if target.exists():
        if target.is_symlink() or not (target/"phase-a.json").is_file():
            raise ValueError("Refusing to replace a non-V4 Phase-A directory.")
    if not apply:
        return {**contract, "dry_run":True,"destination":destination}
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(dir=target.parent,prefix=".phase-a-stage-"))
    backup=target.with_name("."+target.name+".previous")
    if backup.exists() or backup.is_symlink():
        raise ValueError(f"Unremoved previous migration backup: {backup}")
    try:
        for name,data in outputs.items():
            out=staging.joinpath(*name.split("/"))
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(data)
        actual={p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        if actual != set(contract["allowed_files"]):
            raise ValueError("Phase A contract: output files mismatch.")
        existing=target.exists()
        if existing:
            os.replace(target,backup)
        try:
            os.replace(staging,target)
        except BaseException:
            if existing:
                os.replace(backup,target)
            raise
        if existing:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {**contract,"dry_run":False,"destination":destination}


def main(argv: list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,default=Path("."))
    p.add_argument("--source-root",default="okf-batched-generated-v3",
                   help="Root of generated V3 concept Markdown (not original source documents).")
    p.add_argument("--state-root",default="okf-batched/state-v3/docs")
    p.add_argument("--document-root",default="doctrines",
                   help="Workspace-relative directory containing original source Markdown; "
                        "must match the prefix in V3 sections.json (e.g. md).")
    p.add_argument("--destination",default="okf-v4/phase-a")
    p.add_argument("--apply",action="store_true")
    args=p.parse_args(argv)
    print(json.dumps(migrate(args.workspace,source_root=args.source_root,state_root=args.state_root,
                             destination=args.destination,apply=args.apply,
                             document_root=args.document_root),ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
