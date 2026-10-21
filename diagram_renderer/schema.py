"""
schema.py - the intermediate data contract for the LLD renderer.

This is the ONLY thing the LLM has to get right. Everything downstream
(layout, XML, file writing) is deterministic Python and never needs the model.

SECURITY CHANGE: ids and labels are untrusted LLM output. Previously the id check only
rejected the space character, so a newline/tab/quote/angle bracket in an id could reach the
config generator (hostname) and the draw.io XML. Now:
  - Device.id and Link.source/target must be strict identifiers (reject, don't repair).
  - Device.label and Link.label are display text: flattened to one line of printable ASCII
    with markup characters removed (draw.io renders labels as HTML because styles use html=1).
Self-contained on purpose (no cross-package import). Original contract is otherwise unchanged,
including NetworkDiagramSpec.device_ids().
"""

import re
from pydantic import BaseModel, field_validator
from typing import Literal

DeviceType = Literal["router", "switch", "firewall", "server", "cloud", "vlan"]
Tier = Literal["core", "distribution", "access", "edge"]

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")


def _safe_id(v, what: str) -> str:
    if not isinstance(v, str) or not _ID_RE.fullmatch(v):
        raise ValueError(
            f"{what} {ascii(v)[:60]} is not a safe identifier - use only letters, digits, "
            f"'.', '_' and '-' (no spaces or other characters), max 63 chars"
        )
    return v


def _flatten_label(v, max_len: int = 80) -> str:
    s = "".join(ch if " " <= ch <= "~" else " " for ch in str(v))
    s = re.sub(r"[<>&\"'`\\]", " ", s)
    return " ".join(s.split())[:max_len]


class Device(BaseModel):
    id: str          # short, stable, unique - e.g. "core-sw-1"
    label: str       # human-readable - e.g. "Core Switch 1"
    type: DeviceType
    tier: Tier

    @field_validator("id")
    @classmethod
    def id_no_spaces(cls, v: str) -> str:      # name kept for backward compatibility
        return _safe_id(v, "device id")

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        return _flatten_label(v)


class Link(BaseModel):
    source: str
    target: str
    label: str = ""

    @field_validator("source", "target")
    @classmethod
    def _endpoint(cls, v: str) -> str:
        return _safe_id(v, "link endpoint")

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        return _flatten_label(v)


class NetworkDiagramSpec(BaseModel):
    devices: list[Device]
    links: list[Link]

    def device_ids(self) -> set[str]:
        return {d.id for d in self.devices}
