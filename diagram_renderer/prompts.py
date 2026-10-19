"""
prompts.py — the one prompt that touches your Ollama model in this pipeline.
"""

EXTRACTION_PROMPT_TEMPLATE = """You are extracting a network topology from a design document.
Given the LLD text and relevant standards context below, output ONLY a JSON object
matching this schema — no prose, no markdown fences, no explanation.

Each device's "type" field must be exactly ONE of these six words: router, switch, firewall, server, cloud, vlan.
Each device's "tier" field must be exactly ONE of these four words: core, distribution, access, edge.
Never copy a list of options into a field — always pick a single value.

EXAMPLE (structure only — use your own device names and count from the real text below):
{{
  "devices": [
    {{"id": "core-sw-01", "label": "Core Switch 1", "type": "switch", "tier": "core"}},
    {{"id": "dist-sw-01", "label": "Distribution Switch 1", "type": "switch", "tier": "distribution"}},
    {{"id": "fw-01", "label": "Firewall 1", "type": "firewall", "tier": "edge"}}
  ],
  "links": [
    {{"source": "fw-01", "target": "core-sw-01", "label": "1G WAN"}},
    {{"source": "core-sw-01", "target": "dist-sw-01", "label": "10G uplink"}}
  ]
}}

Rules:
- Every "source" and "target" in links must exactly match a device "id" you listed — same spelling, same numbering.
- Ids must be short, lowercase, hyphenated, no spaces (e.g. "core-sw-1").
- Infer "tier" from context: core switches/routers = core, distribution layer = distribution,
  access switches = access, firewalls/WAN/internet = edge.
- If the LLD doesn't specify a detail, make the most reasonable inference — do not leave fields blank.
- COMPLETENESS CHECK: before finishing, count every individually named device in the LLD text
  (including each one in a numbered series like "Access-SW-01 through Access-SW-12" — that is 12
  separate devices, not one). Your "devices" list must contain exactly that many entries. Do not
  summarize or truncate a repetitive series — list every single one individually.

LLD TEXT:
{lld_text}

RELEVANT STANDARDS CONTEXT:
{kb_context}
"""

RETRY_SUFFIX_TEMPLATE = """

Your previous attempt failed validation with this error:
{error}

Please correct the JSON and output ONLY the corrected JSON object, following the same schema.
"""


def build_extraction_prompt(lld_text: str, kb_context: str, retry_error: str | None = None) -> str:
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(lld_text=lld_text, kb_context=kb_context)
    if retry_error:
        prompt += RETRY_SUFFIX_TEMPLATE.format(error=retry_error)
    return prompt
