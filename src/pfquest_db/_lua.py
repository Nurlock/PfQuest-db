"""Shared Lua string serializer for exporters."""

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _lua_str(s: str) -> str:
    return '"' + "".join(
        _ESCAPES.get(c, f"\\{ord(c):03d}" if ord(c) < 0x20 else c) for c in s
    ) + '"'
