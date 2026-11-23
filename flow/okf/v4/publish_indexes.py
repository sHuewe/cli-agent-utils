"""Phase C: link and publish a certified Phase-B corpus deterministically.

Only final reviewed B concepts are copied; no model writes Markdown or
indexes directly. Validate all semantic IDs, internal links and root
navigation before atomically swapping the separately published output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import sys
import tempfile

from migrate_v3 import safe_path, slugify


def _relative(current: str, target: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(current) or ".")


def _escape_label(value: str) -> str:
    # Treat LLM-produced summaries and tags strictly as plain text in
    # generated Markdown, not as permission to inject extra navigation.
    collapsed = " ".join(value.split()).replace("\\", "\\\\")
    return re.sub(r"([`*_\[\]<>!|])", r"\\\1", collapsed)


def render(catalog: dict, tasks: list[dict], summaries: dict[str, dict]) -> tuple[dict[str, bytes], dict]:
    concepts = catalog["concepts"]
    documents = catalog["documents"]
    identity = {c["id"]: c for c in concepts}
    if len(identity) != len(concepts) or set(identity) != set(summaries):
        raise ValueError("Final B inventory does not exactly cover concept IDs.")
    artifacts: dict[str, bytes] = {}
    links: dict[str, list[str]] = {}
    inventory = []
    for c in sorted(concepts,key=lambda x:x["path"]):
        info = summaries[c["id"]]
        inventory.append({
            "id":c["id"], "path":c["path"], "title":c["title"],
            "summary":info["summary"], "tags":info["tags"],
            "document_id":c["document_id"],
            "knowledge_item_ids":c["knowledge_item_ids"],
            "source_path":c["source_path"],
        })

    def index(path: str, header: str, entries: list[tuple[str,str,str]]) -> None:
        if path in artifacts:
            raise ValueError(f"Index collision: {path}")
        rows = [f"# {_escape_label(header)}", ""]
        links[path] = []
        for target, title, description in entries:
            links[path].append(target)
            rows.append(f"- [{_escape_label(title)}]({_relative(path,target)})"
                        + (f" – {_escape_label(description)}" if description else ""))
        if not entries:
            rows.append("_Keine Einträge._")
        rows.append("")
        artifacts[path] = ("\n".join(rows)).encode("utf-8")

    # Nested semantic folders receive their own indexes; root-level
    # doctrine concepts are linked from the doctrine index itself.
    folders: dict[str, list[dict]] = {}
    for c in concepts:
        folder=posixpath.dirname(c["path"])
        folders.setdefault(folder,[]).append(c)
    for folder,members in sorted(folders.items()):
        ix=folder+"/index.md"
        if ix in {c["path"] for c in concepts}:
            raise ValueError(f"Concept path collides with index: {ix}")
        if len(folder.split("/"))==2:
            continue
        index(ix,folder.split("/")[-1].replace("-"," ").title(),
              [(c["path"],c["title"],summaries[c["id"]]["summary"])
               for c in sorted(members,key=lambda c:c["title"].casefold())])

    doc_entries=[]
    for doc in sorted(documents,key=lambda d:d["id"]):
        slug=doc["id"]
        root=f"doctrines/{slug}"
        children=sorted(f for f in folders if f.startswith(root+"/"))
        own=folders.get(root,[])
        if not own and not children:
            raise ValueError(f"Doctrine has no concepts: {slug}")
        entries=[(c["path"],c["title"],summaries[c["id"]]["summary"])
                 for c in sorted(own,key=lambda c:c["title"].casefold())]
        entries.extend((folder+"/index.md",
                        folder.split("/")[-1].replace("-"," ").title(),
                        f"{len(folders[folder])} Konzepte")
                       for folder in children)
        index(root+"/index.md",slug.replace("-"," ").title(),entries)
        count=len(own)+sum(len(folders[f]) for f in children)
        doc_entries.append((root+"/index.md",slug.replace("-"," ").title(),
                            f"{count} Konzepte"))
    index("doctrines/index.md","Doktrinen",doc_entries)

    # LLM tags are semantic labels only. Membership and all paths are generated
    # deterministically from the complete inventory, including global views.
    themes: dict[str,dict] = {}
    for entry in inventory:
        for tag in entry["tags"]:
            key=slugify(tag)
            group=themes.setdefault(key,{"title":tag,"members":[],"member_ids":set()})
            # Distinct labels can normalize to one filename (e.g. an umlaut
            # and its transliteration). Preserve one link per concept ID.
            if entry["id"] not in group["member_ids"]:
                group["members"].append(entry)
                group["member_ids"].add(entry["id"])
    theme_entries=[]
    for key,group in sorted(themes.items()):
        page=f"themen/{key}.md"
        entries=[(item["path"],item["title"],item["summary"])
                 for item in sorted(group["members"],key=lambda x:x["title"].casefold())]
        index(page,group["title"],entries)
        theme_entries.append((page,group["title"],f"{len(entries)} Konzepte"))
    index("themen/index.md","Themen",theme_entries)
    index("index.md","OKF – Wissensübersicht",[
        ("doctrines/index.md","Doktrinen",f"{len(documents)} Dokumente"),
        ("themen/index.md","Themen",f"{len(themes)} thematische Gruppen"),
    ])

    # Source snapshots never enter the published tree. Only final reviewed
    # B concepts, generated indexes, and the semantic inventory are allowed.
    expected_concepts={c["path"] for c in concepts}
    all_paths=set(artifacts)|expected_concepts|{"inventory.json"}
    for page, targets in links.items():
        if len(set(targets))!=len(targets):
            raise ValueError(f"Duplicate navigation link: {page}")
        for target in targets:
            if target not in all_paths:
                raise ValueError(f"Broken generated link {page} -> {target}")
    reachable={"index.md"}
    queue=["index.md"]
    while queue:
        for target in links.get(queue.pop(),[]):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    if not expected_concepts.issubset(reachable):
        raise ValueError("Not every concept is reachable from root index.")
    for folder, members in folders.items():
        actual=set(links[folder+"/index.md"])
        required={c["path"] for c in members}
        if len(folder.split("/"))==2:
            required.update(
                f+"/index.md" for f in folders if f.startswith(folder+"/")
            )
        if actual != required:
            raise ValueError(f"Folder index is not complete: {folder}")
    artifact_inventory={"schema":"okf.inventory.v1","status":"complete","concepts":inventory}
    artifacts["inventory.json"]=(json.dumps(artifact_inventory,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    report={
        "status":"ok","concept_count":len(concepts),
        "document_count":len(documents),"theme_count":len(themes),
        "index_count":len(links),"reachable_concepts":len(expected_concepts),
        "inventory_path":"inventory.json",
    }
    return artifacts,report


def publish(
    workspace: Path, *, phase_b: str, state_root: str,
    destination: str, tasks: dict,
) -> dict:
    """Publish only from certified B; do not modify any B concept file."""
    from phase_b_contract import checked_b
    from prepare_links import prepare as expected_links

    workspace=workspace.resolve()
    _,catalog,base=checked_b(workspace,root=phase_b,stage="B")
    target=safe_path(workspace,destination+"/.placeholder",must_exist=False).parent
    phase_a_root=safe_path(
        workspace,"okf-v4/phase-a/.placeholder",must_exist=False
    ).parent
    # Never publish into, or replace an ancestor of, either immutable input
    # tree. Phase-B validation also depends on Phase A remaining untouched.
    # Check before any output is staged or previous publication is replaced.
    if any(
        target == source or target in source.parents or source in target.parents
        for source in (phase_a_root, base)
    ):
        raise ValueError("Publication root overlaps protected Phase-A/Phase-B input.")
    expected=expected_links(workspace)
    if tasks!=expected:
        raise ValueError("C link tasks differ from the final B inventory.")
    members={c["id"]:c for c in catalog["concepts"]}
    semantic={c["id"]:{"id":c["id"],"summary":c["summary"],
                        "tags":c["tags"]} for c in catalog["concepts"]}
    artifacts,report=render(catalog,tasks["concepts"],semantic)
    # Rewrite and validate pre-existing concept links too: a merge can retire
    # a path that older concepts already referenced. Every old path gets a
    # deterministic redirect to its surviving primary concept.
    from migrate_v3 import _markdown_links
    live_paths={c["path"] for c in catalog["concepts"]}
    link_map={p:p for p in live_paths | set(artifacts)}
    link_map.update(catalog.get("retired_paths",{}))
    link_count=0
    for item in tasks["concepts"]:
        src=members[item["id"]]
        decision=json.loads(safe_path(
            workspace,f"{state_root}/links/{item['key']}.json"
        ).read_text(encoding="utf-8"))
        if not isinstance(decision,dict) or decision.get("source_id")!=item["id"]:
            raise ValueError("Missing or mismatched semantic link review.")
        selected=decision.get("related_ids")
        possibilities={p["id"] for p in item["candidates"]}
        if (not isinstance(selected,list) or len(selected)>5
                or len(selected)!=len(set(selected))
                or not set(selected).issubset(possibilities)):
            raise ValueError("Semantic link proposal has unknown/duplicate IDs.")
        body=_markdown_links(
            (base/src["path"]).read_text(encoding="utf-8"),
            src["path"],src["path"],link_map,
        ).encode("utf-8")
        if selected:
            appendix=["","<!-- okf-generated-links:start -->",
                      "## Verwandte Konzepte",""]
            for ident in selected:
                target=members[ident]
                path=_relative(src["path"],target["path"])
                appendix.append(f"- [{_escape_label(target['title'])}]({path})")
                link_count+=1
            appendix.append("<!-- okf-generated-links:end -->")
            body=body.rstrip(b"\r\n")+("\n"+"\n".join(appendix)+"\n").encode("utf-8")
        artifacts[src["path"]]=body
    report["semantic_links"]=link_count
    # Navigation targets are deterministic and all known; every concept is
    # reachable from root. Verify appended LLM-selected targets by ID above.
    if target.exists() and (target.is_symlink() or not (target/"inventory.json").is_file()):
        raise ValueError("Refusing to overwrite non-C publication.")
    for file in target.rglob("*") if target.exists() else ():
        if file.is_symlink() or (hasattr(file,"is_junction") and file.is_junction()):
            raise ValueError("Existing output tree contains symlinks.")
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(dir=target.parent,prefix=".phase-c-stage-"))
    backup=target.with_name("."+target.name+".previous")
    if backup.exists() or backup.is_symlink():
        raise ValueError("Previous publication backup still exists.")
    try:
        for name,raw in artifacts.items():
            target_file=staging.joinpath(*name.split("/"))
            target_file.parent.mkdir(parents=True,exist_ok=True)
            target_file.write_bytes(raw)
        observed={p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        if observed!=set(artifacts):
            raise ValueError("Incomplete publication output.")
        prior=target.exists()
        if prior:
            os.replace(target,backup)
        try:
            os.replace(staging,target)
        except BaseException:
            if prior:
                os.replace(backup,target)
            raise
        if prior:
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {**report,"published_root":destination,"origin":"certified-phase-b"}


def main(argv: list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,default=Path("."))
    parser.add_argument("--phase-b",default="okf-v4/phase-b")
    parser.add_argument("--state-root",default="okf-v4/state-c")
    parser.add_argument("--destination",default="okf-v4/published")
    args=parser.parse_args(argv)
    envelope=json.load(sys.stdin)
    data=envelope.get("inputs",{}).get("tasks")
    if not isinstance(data,dict):
        raise ValueError("C publisher requires verified json_inputs.tasks.")
    result=publish(args.workspace,phase_b=args.phase_b,state_root=args.state_root,
                   destination=args.destination,tasks=data)
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
