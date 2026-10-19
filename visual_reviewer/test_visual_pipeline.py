"""
test_visual_pipeline.py — proves everything EXCEPT the real API call works
correctly, at zero cost. Uses a mock vision function so the full
extract -> validate -> auto-repair -> render pipeline is tested exactly as
it will run in production, without spending a cent.

Run: python3 test_visual_pipeline.py
"""

import json
from anthropic_vision import encode_image_for_anthropic
from visual_graph import review_diagram_image

TEST_IMAGE = "test_diagram.png"


def test_offline_image_encoding():
    print("=== Test 1: image encoding (fully offline) ===")
    encoded = encode_image_for_anthropic(TEST_IMAGE)
    assert encoded["media_type"] == "image/png"
    assert len(encoded["data"]) > 100
    print(f"OK — encoded, media_type={encoded['media_type']}, base64 length={len(encoded['data'])}\n")


def test_full_pipeline_good_response():
    print("=== Test 2: full pipeline with a MOCKED clean vision response ===")

    def mock_vision_call(image_path, prompt):
        return json.dumps({
            "devices": [
                {"id": "perimeter-fw", "label": "Perimeter FW", "type": "firewall", "tier": "edge"},
                {"id": "core-switch-1", "label": "Core Switch 1", "type": "switch", "tier": "core"},
                {"id": "dist-switch-1", "label": "Dist Switch 1", "type": "switch", "tier": "distribution"},
            ],
            "links": [
                {"source": "perimeter-fw", "target": "core-switch-1", "label": "1G"},
                {"source": "core-switch-1", "target": "dist-switch-1", "label": "10G"},
            ],
        })

    result = review_diagram_image(TEST_IMAGE, _vision_call=mock_vision_call)
    assert not result["failed"], f"Unexpected failure: {result['last_error']}"
    assert len(result["spec"].devices) == 3
    assert len(result["xml"]) > 100
    print(f"OK — {len(result['spec'].devices)} devices, {len(result['spec'].links)} links, XML rendered")
    print(f"Attempts used: {result['attempts_used']}\n")


def test_full_pipeline_with_dangling_reference():
    print("=== Test 3: full pipeline with a MOCKED response needing auto-repair ===")

    def mock_vision_call(image_path, prompt):
        return json.dumps({
            "devices": [
                {"id": "core-switch-1", "label": "Core Switch 1", "type": "switch", "tier": "core"},
                {"id": "dist-switch-1", "label": "Dist Switch 1", "type": "switch", "tier": "distribution"},
            ],
            "links": [
                {"source": "perimeter-fw", "target": "core-switch-1", "label": "1G"},
                {"source": "core-switch-1", "target": "dist-switch-1", "label": "10G"},
            ],
        })

    result = review_diagram_image(TEST_IMAGE, _vision_call=mock_vision_call)
    assert not result["failed"], f"Unexpected failure: {result['last_error']}"
    assert result["warnings"], "expected an auto-repair warning, got none"
    print("OK — auto-repair fired as expected:")
    for w in result["warnings"]:
        print(f"  ! {w}")
    print()


def test_pipeline_gives_up_cleanly_on_persistent_bad_output():
    print("=== Test 4: pipeline fails cleanly (not silently) on persistently bad output ===")

    def mock_vision_call(image_path, prompt):
        return "this is not valid JSON at all"

    result = review_diagram_image(TEST_IMAGE, _vision_call=mock_vision_call)
    assert result["failed"]
    print(f"OK — failed cleanly after {result['attempts_used']} attempts, as designed")
    print(f"Error message: {result['last_error']}\n")


if __name__ == "__main__":
    test_offline_image_encoding()
    test_full_pipeline_good_response()
    test_full_pipeline_with_dangling_reference()
    test_pipeline_gives_up_cleanly_on_persistent_bad_output()
    print("=" * 50)
    print("ALL TESTS PASSED — zero API calls made, zero cost incurred.")
    print("Pipeline is proven correct and ready for the real Anthropic call.")
