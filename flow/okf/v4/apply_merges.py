"""Apply validated optional same-doctrine merges, preserving exact item coverage."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from migrate_v3 import safe_path
from phase_b_contract import checked_b
from refine_b import B_SCHEMA, _semantic, markdown, encode, sha, snapshot
from prepare_merges import prepare as expected_groups


def merge(workspace: Path, *, groups: dict, state: str = "okf-v4/state-b",
          source: str = "okf-v4/b-reviewed",
          destination: str = "okf-v4/b-merged") -> dict:
    marker, catalog, base=checked_b(workspace,root=source,stage="B-draft")
    expected=expected_groups(workspace)
    if groups!=expected:
        raise ValueError("Merge tasks do not match reviewed B corpus.")
    records={c["id"]:dict(c) for c in catalog["concepts"]}
    files={c["path"]:(base/c["path"]).read_bytes() for c in records.values()}
    aliases=dict(catalog["aliases"])
    retired_paths=dict(catalog.get("retired_paths",{}))
    merged=0
    for task in groups["groups"]:
        decision=json.loads(safe_path(
            workspace, f"{state}/merges/{task['key']}.json"
        ).read_text(encoding="utf-8"))
        if not isinstance(decision,dict) or decision.get("group_key")!=task["key"]:
            raise ValueError("Merge decision has incorrect group identity.")
        action=decision.get("action")
        if action=="skip":
            if decision.get("member_ids")!=[]:
                raise ValueError("Skipped merge must have no member IDs.")
            continue
        if action!="merge":
            raise ValueError("Unknown merge action.")
        ids=decision.get("member_ids")
        possible={m["id"] for m in task["members"]}
        if (not isinstance(ids,list) or not 2<=len(ids)<=len(possible)
                or len(set(ids))!=len(ids) or not set(ids).issubset(possible)):
            raise ValueError("Merge references invalid or duplicate member IDs.")
        if any(ident not in records for ident in ids):
            raise ValueError("Overlapping merge selections are not allowed.")
        title=decision.get("title")
        if not isinstance(title,str) or not title.strip():
            raise ValueError("Merged concept must have a meaningful title.")
        body=markdown(title,decision.get("markdown"))
        sem=_semantic({
            "id":ids[0],"summary":decision.get("summary"),"tags":decision.get("tags")
        },ids[0])
        members=[records.pop(cid) for cid in ids]
        if len({c["document_id"] for c in members})!=1:
            raise ValueError("Cross-document concept merges are unsupported.")
        combined=[ki for c in members for ki in c["knowledge_items"]]
        if len({x["id"] for x in combined})!=len(combined):
            raise ValueError("Merge duplicated a source Knowledge Item.")
        # Preserve primary identity/path; redirect only removed identities.
        primary=members[0]
        if title != primary["title"]:
            raise ValueError("Merged primary concept must keep its descriptive filename/title.")
        primary.update({
            "title":title,"sha256":sha(body),"summary":sem["summary"],
            "tags":sem["tags"],
            "knowledge_items":combined,
            "knowledge_item_ids":[ki["id"] for ki in combined],
            "evidence_ranges":[rng for ki in combined
                               for rng in ki.get("evidence_ranges",[])],
            "merged_from":[c["id"] for c in members],
        })
        for c in members:
            files.pop(c["path"])
            if c["id"] != primary["id"]:
                retired_paths[c["path"]] = primary["path"]
        files[primary["path"]]=body
        records[primary["id"]]=primary
        for dropped in ids[1:]:
            aliases[dropped]=primary["id"]
        merged+=len(ids)-1
    final=list(sorted(records.values(),key=lambda c:c["path"]))
    for doc in catalog["documents"]:
        files[doc["source_snapshot"]]=(base/doc["source_snapshot"]).read_bytes()
    updated={
        **catalog,"stage":"B-merged","concepts":final,
        "aliases":aliases,"retired_paths":retired_paths,
        "documents":[
            {**d,"concept_ids":[c["id"] for c in final if c["document_id"]==d["id"]]}
            for d in catalog["documents"]
        ],
    }
    files["catalog.json"]=encode(updated)
    files["merged.json"]=encode({
        "schema":B_SCHEMA,"status":"merged",
        "catalog_sha256":sha(files["catalog.json"]),
        "concept_count":len(final),
        "knowledge_item_count":sum(len(c["knowledge_items"]) for c in final),
    })
    # Enforce exact content and Knowledge-Item equality against the source
    # before a single byte is published into the merged output tree.
    source_items={x["id"]:x for c in catalog["concepts"] for x in c["knowledge_items"]}
    final_items={x["id"]:x for c in final for x in c["knowledge_items"]}
    if source_items!=final_items or sum(map(lambda c:len(c["knowledge_items"]),final))!=len(source_items):
        raise ValueError("Merge violated source coverage.")
    snapshot(workspace,destination,files,"merged.json")
    checked_b(workspace,root=destination,stage="B-merged")
    return {"status":"ok","root":destination,"concept_count":len(final),
            "removed_concepts":merged,"reviewed_groups":len(groups["groups"])}


def main() -> None:
    data=json.load(sys.stdin)
    groups=data.get("inputs",{}).get("groups")
    if not isinstance(groups,dict):
        raise ValueError("Expected verified merge tasks in json_inputs.groups.")
    print(json.dumps(merge(Path(".").resolve(),groups=groups),ensure_ascii=False))


if __name__=="__main__":
    main()
