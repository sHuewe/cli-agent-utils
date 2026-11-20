"""Guard the text-only boundary of the OKF section scan prompt.

Image-only sources may be evaluated separately, while unreadable or omitted
*text* must still fail closed. This is a prompt contract test, not a model
behavior guarantee.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "flow/okf/flow_okf_from_doctrine_batched/prompts/01_scan.md"


def test_scan_prompt_defers_image_only_content_without_failing_text_sweep():
    prompt = PROMPT.read_text(encoding="utf-8")
    assert "TEXT-ONLY SCOPE" in prompt
    assert "image-only plates" in prompt
    assert "do NOT mark a text sweep failed or set needs_attention" in prompt
    assert "both scan_checks sweeps=completed" in prompt
    assert "Record\ntheir presence" in prompt or "Record\ntheir presence".replace("\n", " ") in prompt


def test_scan_prompt_requires_complete_text_and_blocks_real_errors():
    prompt = PROMPT.read_text(encoding="utf-8")
    assert "Extract and preserve\nALL readable text" in prompt
    assert "a source read fails" in prompt
    assert "otherwise omitted, set needs_attention" in prompt
    assert "Do not pretend an\nincomplete text read or extraction was successful" in prompt
    assert "Do not claim the images were\nanalyzed" in prompt


def test_scan_flow_retains_strict_outline_validation():
    flow = (
        ROOT / "flow/okf/flow_okf_from_doctrine_batched/flows/build-document.toml"
    ).read_text(encoding="utf-8")
    assert 'kind = "prepare_outline_tasks"' in flow
    assert 'overwrite_output = false' in flow
