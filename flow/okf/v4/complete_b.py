"""Complete Phase B with a fresh LLM inventory of final revised concepts."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from phase_b_contract import checked_b
from migrate_v3 import safe_path
from refine_b import B_SCHEMA, encode, sha, snapshot, validate_tasks, summary


def complete(workspace: Path, *, tasks: dict, state: str = "okf-v4/state-b",
             source: str = "okf-v4/b-merged",
             destination: str = "okf-v4/phase-b") -> dict:
    _,catalog,base=checked_b(workspace,root=source,stage="B-merged")
    verified=validate_tasks(tasks,catalog,source)
    llm={}
    for t in verified:
        result=json.loads(safe_path(
            workspace,f"{state}/final/verification/{t['key']}.json"
        ).read_text(encoding="utf-8"))
        if (not isinstance(result,dict) or result.get("id")!=t["id"]
                or result.get("status")!="ok"
                or result.get("missing_item_ids")!=[]
                or result.get("warnings")!=[]):
            raise ValueError(f"Final semantic verification failed: {t['id']}")
        llm[t["id"]]=summary(workspace,state+"/final",t)
    next_concepts=[]
    inventory=[]
    for concept in catalog["concepts"]:
        current={**concept,**llm[concept["id"]]}
        next_concepts.append(current)
        inventory.append({
            "id":current["id"], "path":current["path"],
            "title":current["title"],
            "summary":current["summary"],"tags":current["tags"],
            "sha256":current["sha256"],
            "document_id":current["document_id"],
            "knowledge_item_ids":current["knowledge_item_ids"],
            "source_path":current["source_path"],
        })
    next_catalog={**catalog,"stage":"B","concepts":next_concepts}
    data_inventory={"schema":"okf.inventory.v1","status":"complete","concepts":inventory}
    files={c["path"]:(base/c["path"]).read_bytes() for c in next_concepts}
    for doc in next_catalog["documents"]:
        files[doc["source_snapshot"]]=(base/doc["source_snapshot"]).read_bytes()
    files["catalog.json"]=encode(next_catalog)
    files["inventory.json"]=encode(data_inventory)
    files["phase-b.json"]=encode({
        "schema":B_SCHEMA,"stage":"B","status":"completed",
        "catalog_sha256":sha(files["catalog.json"]),
        "inventory_sha256":sha(files["inventory.json"]),
        "concept_count":len(next_concepts),
        "knowledge_item_count":sum(len(c["knowledge_items"]) for c in next_concepts),
        "source_phase_a_sha256":next_catalog["origin_phase_a_sha256"],
    })
    snapshot(workspace,destination,files,"phase-b.json")
    checked_b(workspace,root=destination,stage="B")
    return {"status":"completed","phase":"B","root":destination,
            "concept_count":len(next_concepts),
            "inventory_count":len(inventory)}


def main() -> None:
    envelope=json.load(sys.stdin)
    tasks=envelope.get("inputs",{}).get("tasks")
    if not isinstance(tasks,dict):
        raise ValueError("Expected verified final inventory tasks.")
    print(json.dumps(complete(Path(".").resolve(),tasks=tasks),ensure_ascii=False))


if __name__=="__main__":
    main()
