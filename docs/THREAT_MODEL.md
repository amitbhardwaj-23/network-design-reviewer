# ARGUS Threat Model (v0.2, security step 1)

## Scope and assets
LLD text / hand-drawn diagrams (untrusted) -> LLM extraction -> pydantic validation -> deterministic
renderer -> draft config -> (future) human diff review -> NAPALM push to devices.
Assets: network devices (config integrity), Anthropic API key and spend, the ARGUS host, user trust in output.

## Trust boundaries
1. Uploaded document/diagram -> LLM (prompt injection possible; LLM output is untrusted).
2. LLM output -> schema validators (the primary control).
3. Renderer -> device (config text is line-oriented; a newline is a new command).
4. ARGUS UI -> LAN (currently unauthenticated).

## Findings
| ID | Finding | Severity | Status |
|----|---------|----------|--------|
| F1 | Streamlit UI unauthenticated, bound 0.0.0.0:8501 | High | MITIGATED - ufw allows 8501 from the LAN subnet only; see F12 |
| F2 | Config injection via newline in extracted strings (proven against original code: live `username`, `enable secret`, `line vty`, hijacked `ip route`) | Critical | FIXED - 3 layers (field allowlists, render sanitizers, line-allowlist lint) |
| F3 | Placeholder secrets (`AUTH_PASSWORD`), `<x-ip>`, `interfaceUNSPECIFIED-N`, default SNMP `public` in drafts | High | MITIGATED - `assert_pushable()` blocks; must be wired into `PushSession.stage()` in push phase |
| F4 | Prompt injection can still skew data-level values (VLAN IDs, IPs) | Medium | RESIDUAL - delimiters + data-only instruction; real controls: validators, human diff review, push allowlist; planned provenance check |
| F5 | Retry loop echoes validator error (attacker text) back to LLM | Low | FIXED - printable ASCII, 500 chars |
| F6 | draw.io XML / HTML label escaping, Streamlit unsafe_allow_html | Medium | MOSTLY FIXED - render.py escapes & < > " correctly; labels are HTML in draw.io (html=1) so the schema strips markup characters; ids are strict. app.py unsafe_allow_html still to be reviewed |
| F7 | Secrets in repo | High | FIXED - .env ignored, history rewritten, no key ever pushed |
| F8 | Non-ASCII in generated config | Low | FIXED - ASCII only, lint enforced |
| F9 | Push needs least privilege | High | PLANNED (below) |
| F10 | Upload size/type limits, API spend | Medium | OPEN - set `--server.maxUploadSize`, API key spend limit |
| F11 | Review agent looped to the recursion limit on odd input (message history was overwritten each pass, so the model never saw tool results); raw error shown | Medium (reliability) | FIXED - add_messages reducer, 3-round tool cap, friendly failure message, design text wrapped as untrusted data |
| F12 | UI reachable by anyone on the LAN, no login (firewall allows 192.168.1.0/24 only on 8501) | Medium | ACCEPTED for the lab - revisit with auth proxy or app login before wider use |

## Controls
Reject-not-repair validators for security failures; auto-repair-with-warning only for benign gaps.
`fullmatch` + explicit ASCII classes; split on "\n" only. Last-gate line allowlist independent of upstream checks.

## Residual risk
A fully valid but wrong value (e.g. attacker-chosen VLAN 99) passes validators. Mitigate with mandatory human diff review
and device/command allowlists before any push.

## Least-privilege push plan
Separate read vs push credentials; TACACS+ command authorization or restricted privilege level; push worker separated from
the LLM-facing service; no credentials in LLM context; commit-confirm/rollback; device allowlist; audit log; scoped API key
with spend limit.

## Test coverage
`config_generator/test_security.py` (65 checks: schema rejections, benign positives, render, lint-bypass simulation,
prompt hardening, diagram schema). Red-team inputs in `config_generator/redteam/` for manual UI runs.

## Known caveats
Strict validators may reject legitimate text (e.g. descriptions with `'` or `;`, interface ranges, `dhcp`) - tune after
running your sample LLDs. `ip address 10.0.10.1` without a mask is invalid IOS (functional gap, not security).
