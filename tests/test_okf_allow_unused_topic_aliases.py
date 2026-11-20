"""Verify that unused topic aliases do not block completed OKF scans.

This tests the declared Flow policy, not the generic cli-agent join
implementation, which still requires every source item to be mapped.
"""
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "flow/okf/flow_okf_from_doctrine_batched/flows/finish-document.toml"


def test_assign_allows_unused_candidates_but_preserves_source_item_join():
    flow = tomllib.loads(FLOW.read_text(encoding="utf-8"))
    assign = next(step for step in flow["steps"] if step["id"] == "assign")
    op = assign["json_operation"]
    assert op["kind"] == "json_join_aliases"
    assert op["require_all_aliases"] is False
    assert op["items_path"] == "/*/knowledge_items/*"
    assert op["item_key_path"] == "/topic_key"
    assert op["item_id_path"] == "/id"
    assert op["mapping_path"] == "/concepts/*"
    assert op["mapping_alias_path"] == "/merged_from/*"
    assert op["mapping_id_path"] == "/id"
    assert assign["output"].endswith("/assign.json")
    assert assign["overwrite_output"] is False
