"""
visual_prompts.py — the vision-extraction prompt. Deliberately targets the
SAME NetworkDiagramSpec schema the Diagram Renderer already produces from
text, so everything downstream (validate.py's auto-repair, the same
device/tier vocabulary) is proven, reused code — the only new thing is the
image going in.
"""

VISUAL_EXTRACTION_PROMPT = """You are extracting a network topology from an uploaded diagram image.
Look at the image carefully and identify every distinct device (box/shape) and every
connection (line) between devices.

Output ONLY a JSON object matching this schema — no prose, no markdown fences, no explanation.

Each device's "type" field must be exactly ONE of these six words: router, switch, firewall, server, cloud, vlan.
Each device's "tier" field must be exactly ONE of these four words: core, distribution, access, edge.
Never copy a list of options into a field — always pick a single value.

EXAMPLE (structure only — these are placeholder demo values, not real data;
extract your own actual values from the image, and output an EMPTY list if
you cannot clearly identify any devices):
{
  "devices": [
    {"id": "device-1", "label": "Label as shown in the image", "type": "switch", "tier": "core"}
  ],
  "links": [
    {"source": "device-1", "target": "device-2", "label": "Label on the connecting line, if visible"}
  ]
}

Rules:
- Base ids on the label text visible in the image, lowercased and hyphenated (e.g. a box
  labeled "Core Switch 1" becomes id "core-switch-1").
- Every "source" and "target" in links must exactly match a device "id" you listed.
- Infer "tier" from vertical/logical position in the diagram: devices drawn higher or
  labeled as core/backbone = core; middle layer = distribution; bottom/edge devices
  connecting to end-users = access; firewalls, WAN routers, internet clouds = edge.
- If a device's type isn't visually obvious, infer the most likely type from its label
  text and its position in the topology.
- If the image is unclear, blurry, or you cannot confidently identify a shape as a
  specific device, do not guess — omit it rather than inventing a plausible-looking entry.
- COMPLETENESS CHECK: before finishing, re-scan the image for every distinct box/shape —
  do not skip any that are visually present, including ones that look similar to others.
"""

RETRY_SUFFIX_TEMPLATE = """

Your previous attempt failed validation with this error:
{error}

Please look at the image again and output corrected JSON, following the same schema.
"""


def build_visual_extraction_prompt(retry_error: str | None = None) -> str:
    prompt = VISUAL_EXTRACTION_PROMPT
    if retry_error:
        prompt += RETRY_SUFFIX_TEMPLATE.format(error=retry_error)
    return prompt
