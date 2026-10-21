"""
config_sanitize.py - input hardening and last-gate linting for generated device config.

Why this exists
---------------
Everything the LLM extracts (device ids, labels, descriptions, VLAN names, interface
names, IPs) is UNTRUSTED: it can be steered by the LLD text, by text inside an uploaded
diagram, or by plain model error. The renderer writes those strings straight into
line-oriented CLI config, so a single embedded newline turns a "description" into a
brand-new command (e.g. "username x privilege 15 secret y").

Three layers, so no single bug is enough:
  1. Field validators (used by config_schema.py): strict allowlists, reject on failure.
  2. Render-time sanitizers (used by config_render.py): hostnames are validated,
     comment-only text is flattened to printable ASCII.
  3. lint_config(): every rendered line must fully match a pattern the generator
     itself can emit. Anything else - an unknown command, a control character, a
     non-ASCII lookalike - fails the whole device. This layer does not trust layers 1-2.

Security failures are never auto-repaired. ARGUS auto-repairs benign gaps (a missing
interface name) with a visible warning; it hard-stops on anything that looks like
injection, because the cost of a wrong guess here is a compromised device.

Design rules: fullmatch only (never `$`, which tolerates a trailing newline), explicit
ASCII classes (never \\d or \\w, which match Unicode), split lines on "\\n" only (never
splitlines(), which would silently swallow \\r, \\x85, \\u2028 and hide them from the check).
"""
from __future__ import annotations

import ipaddress
import re


class ConfigSecurityError(Exception):
    """Generated config failed a security gate. Do not auto-repair; stop and surface it."""


# --------------------------------------------------------------------------- allowlists
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")          # device ids / hostnames
_IFACE_RE = re.compile(r"[A-Za-z][A-Za-z0-9/._:-]{0,47}")           # Gi1/0/1, Vlan10, Te0/0/1.100
_TEXT_CHARS = r"A-Za-z0-9 _.,:/()+#@&-"                              # no ? ; | $ ` < > \ " ' ! %
_TEXT_RE = re.compile(rf"[{_TEXT_CHARS}]*")
_SUBNET_RE = re.compile(r"[0-9A-Fa-f:./]{0,64}")


def _preview(value, n: int = 60) -> str:
    """Safe-to-print rendering of an untrusted value (newlines/non-ASCII shown escaped)."""
    s = ascii(value)
    return s if len(s) <= n else s[:n] + "...'"


# --------------------------------------------------------------------------- validators
def check_name(value, what: str = "name") -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ValueError(
            f"{what} {_preview(value)} is not a safe identifier "
            f"(letters, digits, '.', '_', '-' only; 1-63 chars; must start with a letter or digit)"
        )
    return value


def check_interface_name(value, what: str = "interface_name") -> str:
    if not isinstance(value, str) or not _IFACE_RE.fullmatch(value):
        raise ValueError(
            f"{what} {_preview(value)} is not a valid interface name "
            f"(start with a letter; letters, digits and / . _ : - only; max 48 chars; no spaces)"
        )
    return value


def check_free_text(value, what: str, max_len: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text")
    if len(value) > max_len:
        raise ValueError(f"{what} is longer than {max_len} characters")
    if not _TEXT_RE.fullmatch(value):
        raise ValueError(
            f"{what} contains characters that are not allowed in device config text: {_preview(value)}"
        )
    return value


def check_int_range(value, lo: int, hi: int, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (lo <= value <= hi):
        raise ValueError(f"{what} {_preview(value)} is out of range {lo}-{hi}")
    return value


def check_vlan_id(value, what: str = "VLAN id") -> int:
    return check_int_range(value, 1, 4094, what)


def _ipv4(s: str) -> ipaddress.IPv4Address:
    if not s.isascii():
        raise ValueError("non-ASCII address")
    return ipaddress.IPv4Address(s)


def check_ipv4_host(value, what: str = "address") -> str:
    """A bare dotted-quad IPv4 address (used for gateways / next hops)."""
    try:
        if not isinstance(value, str):
            raise ValueError
        _ipv4(value)
    except ValueError:
        raise ValueError(f"{what} {_preview(value)} is not a valid IPv4 address") from None
    return value


def check_interface_ip(value, what: str = "ip_address") -> str:
    """Interface address in one of: 'a.b.c.d', 'a.b.c.d/nn', 'a.b.c.d m.m.m.m'."""
    try:
        if not isinstance(value, str) or not value.isascii():
            raise ValueError
        if "/" in value:
            addr, _, plen = value.partition("/")
            _ipv4(addr)
            if not (plen.isdigit() and len(plen) <= 2 and 0 <= int(plen) <= 32):
                raise ValueError
        elif " " in value:
            parts = value.split(" ")
            if len(parts) != 2:
                raise ValueError
            _ipv4(parts[0])
            inv = int(_ipv4(parts[1])) ^ 0xFFFFFFFF
            if inv & (inv + 1):                      # netmask bits must be contiguous
                raise ValueError
        else:
            _ipv4(value)
    except ValueError:
        raise ValueError(
            f"{what} {_preview(value)} is not a valid IPv4 interface address "
            f"(use a.b.c.d, a.b.c.d/nn or a.b.c.d mask)"
        ) from None
    return value


def check_subnet_chars(value, what: str = "subnet") -> str:
    """Subnet is not rendered today; restrict to address characters so it stays safe if it ever is."""
    if not isinstance(value, str) or not _SUBNET_RE.fullmatch(value):
        raise ValueError(f"{what} {_preview(value)} contains characters that are not allowed")
    return value


# --------------------------------------------------------------------------- render-time helpers
def comment_text(value, max_len: int = 80) -> str:
    """Flatten any value to printable single-line ASCII for use inside a '!' comment.
    Newlines, control characters and non-ASCII all become spaces."""
    s = "".join(ch if " " <= ch <= "~" else " " for ch in str(value))
    return " ".join(s.split())[:max_len]


# --------------------------------------------------------------------------- layer 3: line lint
_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}"
_IFACE = r"[A-Za-z][A-Za-z0-9/._:-]{0,47}"
_TEXT = rf"[{_TEXT_CHARS}]*"

# Every line the generator can legitimately emit. Anything else is a violation.
_ALLOWED_LINE_PATTERNS = [
    re.compile(p)
    for p in (
        r"",                                                   # blank
        r"![ -~]*",                                            # comment: '!' + printable ASCII only
        rf"hostname {_NAME}",
        r"vlan [0-9]{1,4}",
        rf" name {_TEXT}",
        rf"interface {_IFACE}",
        rf" description {_TEXT}",
        r" ip address [0-9./ ]{7,31}",
        r" standby 1 ip [0-9.]{7,15}",
        r" standby 1 priority [0-9]{1,3}",
        r" standby 1 preempt",
        r" no shutdown",
        r" switchport access vlan [0-9]{1,4}",
        r" switchport mode (access|trunk)",
        r" switchport trunk allowed vlan [0-9]{1,4}(,[0-9]{1,4})*",
        r" spanning-tree portfast",
        r" spanning-tree bpduguard enable",
        r" switchport port-security",
        r" switchport port-security maximum [0-9]{1,4}",
        r" switchport port-security violation restrict",
        r" authentication port-control auto",
        r" dot1x pae authenticator",
        r"snmp-server community public RO",
        r"snmp-server group ARGUS-SNMPv3 v3 priv",
        r"snmp-server user argus-admin ARGUS-SNMPv3 v3 auth sha AUTH_PASSWORD priv aes 128 PRIV_PASSWORD",
        rf"ip route 0\.0\.0\.0 0\.0\.0\.0 <{_NAME}-ip>",
        r"end",
    )
]


def lint_config(text: str) -> list[tuple[int, str]]:
    """Return [(line_no, reason)] for every line that is not an allowed generator line."""
    problems: list[tuple[int, str]] = []
    for n, line in enumerate(text.split("\n"), 1):      # split on \n ONLY (see module docstring)
        if not any(p.fullmatch(line) for p in _ALLOWED_LINE_PATTERNS):
            problems.append((n, f"line not in generator allowlist: {_preview(line, 80)}"))
    return problems


def assert_safe_config(text: str, device_id: str = "?") -> None:
    problems = lint_config(text)
    if problems:
        shown = "; ".join(f"line {n}: {why}" for n, why in problems[:5])
        more = f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""
        raise ConfigSecurityError(
            f"Generated config for {_preview(device_id, 40)} failed the security gate "
            f"({len(problems)} problem line(s)): {shown}{more}"
        )


# --------------------------------------------------------------------------- deployability blockers
_PLACEHOLDER_RE = re.compile(r"AUTH_PASSWORD|PRIV_PASSWORD|interfaceUNSPECIFIED-[0-9]+|<[^>\n]*>")
_INSECURE_DEFAULTS = [
    (re.compile(r"snmp-server community (public|private)\b"), "well-known default SNMP community string"),
]


def find_blockers(text: str) -> list[dict]:
    """Things that are fine in a REVIEW draft but must never reach a device:
    unresolved placeholders (a literal 'AUTH_PASSWORD' would become a real, guessable
    SNMPv3 password) and well-known default credentials."""
    out: list[dict] = []
    for n, line in enumerate(text.split("\n"), 1):
        if line.startswith("!"):
            continue
        m = _PLACEHOLDER_RE.search(line)
        if m:
            out.append({"line": n, "kind": "unresolved_placeholder", "detail": m.group(0)})
        for rx, why in _INSECURE_DEFAULTS:
            if rx.search(line):
                out.append({"line": n, "kind": "insecure_default", "detail": why})
    return out


def assert_pushable(text: str, device_id: str = "?") -> None:
    """Gate for the push stage: line lint AND no deployability blockers."""
    assert_safe_config(text, device_id)
    blockers = find_blockers(text)
    if blockers:
        shown = "; ".join(f"line {b['line']}: {b['kind']} ({b['detail']})" for b in blockers[:5])
        raise ConfigSecurityError(
            f"Config for {_preview(device_id, 40)} is a review draft, not deployable "
            f"({len(blockers)} blocker(s)): {shown}"
        )
