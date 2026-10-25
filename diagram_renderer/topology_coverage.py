"""
topology_coverage.py - deterministic check that the extracted topology contains every device the
LLD text names. No LLM. Self-contained (no cross-package imports).

A device-like name is hyphenated and ends in digits or a single letter: Core-FW-01, WAN-RTR-01,
ISP-A. Prose such as "north-south", "Low-Level" or "chassis-to-chassis" does not match.
Names are compared case-insensitively.
"""
import re

_DEVICE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-(?:[0-9]+|[A-Za-z])(?![A-Za-z0-9_-])"
)


def named_devices(lld_text: str) -> set:
    return {m.group(0).lower() for m in _DEVICE_TOKEN.finditer(lld_text or "")}


def find_missing_devices(lld_text: str, spec) -> list:
    known = {d.id.lower() for d in spec.devices}
    return sorted(named_devices(lld_text) - known)


def find_unlinked_devices(spec) -> list:
    linked = set()
    for l in spec.links:
        linked.add(l.source)
        linked.add(l.target)
    return sorted(d.id for d in spec.devices if d.id not in linked)
