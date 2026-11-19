"""Regression checks for incremental, checkpoint-compatible JSON model contracts.

The schemas constrain *new* model responses. They must not change legacy
step identities, paths, or foreach iteration IDs, because old JSON checkpoints
are reused by the same Flow invocation.
"""
from pathlib import Path
import json
import tomllib

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "flow" / "okf" / "flow_okf_from_doctrine_batched"
SCHEMA_DIR = BASE / "schemas"


def steps(rel):
    obj = tomllib.loads((BASE / rel).read_text(encoding="utf-8"))
    return {step["id"]: step for step in obj["steps"]}


def test_schema_files_resolve_and_are_bounded_json_draft_202012():
    for flow in (BASE / "flows").glob("*.toml"):
        for step in steps(str(flow.relative_to(BASE))).values():
            if "output_schema" not in step:
                continue
            assert step["response_format"] == "json"
            file = ROOT / step["output_schema"]
            assert file.is_file(), (flow, step["id"])
            assert file.stat().st_size <= 65536
            schema = json.loads(file.read_text(encoding="utf-8"))
            assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            Draft202012Validator.check_schema(schema)
            assert schema["type"] == "object"
            assert "required" in schema
            assert step.get("overwrite_output", False) is False
    assert len(list(SCHEMA_DIR.glob("*.schema.json"))) >= 10


def test_existing_golden_and_okf_checkpoint_identities_are_preserved():
    root = steps("flow.toml")
    assert root["analyze_documents"]["flow"].endswith("/analyze-document.toml")
    assert root["build_modules"]["iteration_id"] == "${item.slug}"
    doc = steps("flows/build-document.toml")
    assert doc["scan"]["iteration_id"] == "${item.id}"
    assert doc["scan"]["output"].endswith("/scan-${iteration.id}.json")
    assert doc["section_outlines"]["output"].endswith("/outline-${iteration.id}.json")
    finish = steps("flows/finish-document.toml")
    assert finish["taxonomy"]["output"].endswith("/taxonomy.json")
    assert finish["consolidate"]["iteration_id"] == "${item.id}"
    assert finish["consolidate"]["output"].endswith(
        "/consolidation-${iteration.id}.json"
    )
    assert finish["validated_batches"]["iteration_id"] == "${item.id}"
    assert finish["consolidated"]["output"].endswith("/consolidated.json")
    concept = steps("flows/build-concept.toml")
    for name in ("build", "verify", "repair"):
        assert concept[name]["output"].endswith(
            f"/concept-${{input.concept.id}}-{name}.json"
        )
    assert concept["manifest"]["output"].endswith(
        "/manifests/concept-${input.concept.id}.json"
    )


def test_original_consolidation_can_reach_repair_but_repaired_output_is_strict():
    original = steps("flows/finish-document.toml")["consolidate"]
    repair = steps("flows/validate-consolidation.toml")["repair"]
    assert original["output_schema"] != repair["output_schema"]
    source_schema = json.loads((ROOT / original["output_schema"]).read_text(encoding="utf-8"))
    repair_schema = json.loads((ROOT / repair["output_schema"]).read_text(encoding="utf-8"))
    before = source_schema["properties"]["groups"]["items"]
    after = repair_schema["properties"]["groups"]["items"]
    # Invalid existing source folder references must remain available to the
    # conditional correction step, not rejected at checkpoint preflight.
    assert "folder_id" not in before["required"]
    assert before["properties"]["folder_id"] == {}
    assert "folder_id" in after["required"]
    assert "null" in after["properties"]["folder_id"]["type"]
    assert steps("flows/validate-consolidation.toml")["recheck"][
        "json_operation"
    ]["on_invalid"] == "raise"


def test_existing_schema_contracts_allow_legacy_extra_fields():
    # Existing resume state has historically allowed additional model output
    # fields: adding strict additionalProperties=false could invalidate data.
    for path in SCHEMA_DIR.glob("*.schema.json"):
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert obj.get("additionalProperties") is not False, path


def test_nonconforming_verify_status_from_older_runs_is_not_rejected_by_schema():
    # Earlier models occasionally returned 'needs_attention' despite the prompt.
    # The content QC flow, not a checkpoint schema change, must address those.
    schema = json.loads((SCHEMA_DIR / "concept-verify.schema.json").read_text())
    assert "enum" not in schema["properties"]["status"]


def test_runtime_schema_enums_enforce_exact_concept_identity():
    concept = steps("flows/build-concept.toml")
    expected_id = {"ref": "input.concept_id_options"}
    expected_path = {"ref": "input.concept_result_path_options"}
    for name in ("build", "verify", "repair"):
        enums = concept[name]["output_schema_enums"]
        assert enums["/properties/concept_id"] == expected_id["ref"]
        assert enums["/properties/path"] == expected_path["ref"]
    manifest = concept["manifest"]["output_schema_enums"]
    assert manifest["/properties/source_slug"] == "input.source_slug_options"
    assert manifest["/properties/source_path"] == "input.source_path_options"
    assert manifest["/properties/concepts/items/properties/path"] == (
        "input.concept_path_options"
    )
    assert manifest["/properties/concepts/items/properties/source_slug"] == (
        "input.source_slug_options"
    )
    assert manifest["/properties/concepts/items/properties/source_path"] == (
        "input.source_path_options"
    )

    caller = steps("flows/finish-document.toml")["build_concepts"]["input"]
    assert caller["concept_id_options"] == ["${item.id}"]
    assert caller["concept_path_options"] == ["${item.path}"]
    assert caller["concept_result_path_options"] == [
        "${item.path}", "${input.okf_root}/${item.path}"
    ]
    assert caller["source_slug_options"] == ["${input.source.slug}"]
    assert caller["source_path_options"] == ["${input.source.path}"]
    child_inputs = tomllib.loads((BASE / "flows/build-concept.toml").read_text())["inputs"]
    assert set(caller) == set(child_inputs)


def test_each_batched_model_step_has_json_schema_without_changing_output_paths():
    for flow in sorted((BASE / "flows").glob("*.toml")):
        for step in steps(str(flow.relative_to(BASE))).values():
            if "prompt_file" in step:
                assert step.get("output_schema", "").startswith(
                    "flow/okf/flow_okf_from_doctrine_batched/schemas/"
                ), (flow, step["id"])
                assert step.get("response_format") == "json"
                assert not step.get("overwrite_output", False)


def test_known_legacy_and_repaired_consolidation_payloads_are_compatible():
    # Old cached consolidation responses sometimes contain invalid/missing
    # folder IDs. Those must flow into validation/repair, not be rejected
    # during checkpoint loading by an overly strict new schema.
    old = json.loads((SCHEMA_DIR / "consolidation.schema.json").read_text())
    repaired = json.loads((SCHEMA_DIR / "consolidation-repaired.schema.json").read_text())
    legacy = {
        "status": "ok",
        "groups": [{
            "member_ids": ["s001-t001"],
            "title": "Existing concept",
            "description": "Existing summary",
            "folder_id": {"wrong": "shape"},
        }],
        "warnings": [],
    }
    Draft202012Validator(old).validate(legacy)
    assert list(Draft202012Validator(repaired).iter_errors(legacy))
    missing = {"status": "ok", "groups": [{
        "member_ids": ["s001-t001"],
        "title": "Existing concept",
        "description": "Existing summary",
    }]}
    Draft202012Validator(old).validate(missing)
    assert list(Draft202012Validator(repaired).iter_errors(missing))
    corrected = {**missing, "groups": [{**missing["groups"][0], "folder_id": "rules"}]}
    Draft202012Validator(repaired).validate(corrected)


def test_previous_nonstandard_verify_status_is_valid_old_checkpoint():
    schema = json.loads((SCHEMA_DIR / "concept-verify.schema.json").read_text())
    old = {"status": "needs_attention", "concept_id": "s056-t001",
           "path": "doctrines/a/s056-t001.md", "documented_item_ids": []}
    Draft202012Validator(schema).validate(old)


def test_legacy_root_prefixed_concept_output_uses_exact_concrete_enum():
    """Previously persisted model results may include the configured OKF root."""
    from jsonschema import Draft202012Validator

    child = steps("flows/build-concept.toml")
    parent = steps("flows/finish-document.toml")["build_concepts"]["input"]
    canonical = "doctrines/md-2026/cell-role-and-authority/s001-t001.md"
    root = "okf-batched-generated-v3"
    options = [canonical, f"{root}/{canonical}"]
    assert parent["concept_result_path_options"] == [
        "${item.path}", "${input.okf_root}/${item.path}"
    ]
    assert parent["concept_path_options"] == ["${item.path}"]

    for name in ("build", "verify", "repair"):
        step = child[name]
        assert step["output_schema_enums"]["/properties/path"] == (
            "input.concept_result_path_options"
        )
        schema = json.loads((ROOT / step["output_schema"]).read_text())
        schema["properties"]["path"]["enum"] = options
        required = {
            "build": {"status": "created", "documented_item_ids": []},
            "verify": {"status": "ok", "documented_item_ids": []},
            "repair": {"status": "ok", "documented_item_ids": []},
        }[name]
        for path in options:
            Draft202012Validator(schema).validate({
                "concept_id": "s001-t001", "path": path, **required
            })
        assert list(Draft202012Validator(schema).iter_errors({
            "concept_id": "s001-t001", "path": "other-root/" + canonical,
            **required
        }))

    # Manifest must always use the canonical relative path, not a root prefix.
    manifest = child["manifest"]["output_schema_enums"]
    assert manifest["/properties/concepts/items/properties/path"] == (
        "input.concept_path_options"
    )
