# Topology LLD (red-team 05: hostile device names)
Devices: "core-sw-01\nline vty 0 15", "sw<script>alert(1)</script>", "fw 01".
Expected: ids rejected/sanitized by diagram schema; ConfigSecurityError at render if any slip through.
