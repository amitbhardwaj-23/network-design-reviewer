# Config Generator — Module 3, drop-in for network-design-reviewer

Reuses the Diagram Renderer's proven topology extraction (devices, links,
tiers, auto-repair) — this module adds ONE new small LLM extraction
(config parameters: VLANs, interfaces, security settings) on top, then
deterministic Python assembles Cisco-style config text.

## 1. Copy files onto the VM

```bash
mkdir -p ~/network-design-reviewer/config_generator
# scp/paste config_schema.py, config_prompts.py, config_validate.py,
# config_render.py, config_graph.py, test_config_pipeline.py into it
touch ~/network-design-reviewer/config_generator/__init__.py
```

## 2. Test the deterministic half first (no Ollama needed)

```bash
cd ~/network-design-reviewer/config_generator
source ../venv/bin/activate
python3 test_config_pipeline.py
```

You should see: validation correctly drop an intentionally-bad device_id
with a warning, then three rendered `.cfg` blocks printed (core switch with
VLANs/HSRP/routing, access switch with port config, firewall — currently an
empty shell, see the known limitation below), then confirmation they were
written to `test_config_output/`.

## 3. Test the real end-to-end pipeline (uses Ollama, reuses the Diagram Renderer)

```bash
python3 -c "
from config_graph import generate_configs_for_lld

lld_text = '''[paste any of the sample LLDs you already tested today]'''

result = generate_configs_for_lld(lld_text=lld_text, kb_context='')
print('failed:', result.get('failed'))
print('last_error:', result.get('last_error'))
print('warnings:', result.get('warnings'))
print('diagram_output_path:', result.get('diagram_output_path'))
print('config_paths:', result.get('config_paths'))
"
```

This will take longer than the Diagram Renderer alone — it's now doing TWO
LLM calls in sequence (topology, then config params) instead of one. Let it
run fully undisturbed.

**Expect it to inherit today's known model limitations** — if the topology
extraction drops or hallucinates a device, that's the same underlying
`llama3.2` behavior we spent today hardening against, now surfacing here
too. The auto-repair and warnings should catch it the same way.

## 4. Known limitations — real gaps, not hidden

- **Firewall/router config is a shell only.** The interface/security schema
  is switch-oriented (access/trunk/SVI). NAT rules, ACLs, and BGP peering
  aren't modeled yet — this is the natural next thing to extend once you've
  tested this against a real design and can see what's actually missing.
- **IP addresses are only included where the LLD explicitly states them.**
  If your design doesn't give per-device IPs, the generated config will
  have gaps (e.g. `ip route 0.0.0.0 0.0.0.0 <fw-01-ip>` as a placeholder,
  not a real IP) — intentional, since inventing an IP would be worse than
  flagging it's missing.
- **No `app.py` wiring yet** — this module works standalone, same as the
  Diagram Renderer did before we wired its button in. Worth doing once
  you've validated the output against a real document first.

## What's tested vs. what to watch for

Tested: JSON validation (including auto-repair-by-omission for bad
device_ids), Cisco-style template rendering for switch access/trunk/routed
interfaces, HSRP, port security, SNMP (including a security warning
comment for SNMPv2c). All deterministic, no Ollama dependency.

Not yet tested: the real two-stage LLM pipeline against your actual sample
designs. Same advice as the Diagram Renderer — check the extracted JSON
before worrying about the final config text; if the structured data is
right, the rendered config is guaranteed right, since templating is
deterministic.
