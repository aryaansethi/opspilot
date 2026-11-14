"""Escaping for untrusted text placed inside <evidence> blocks in LLM prompts.

Retrieved documents, log lines and tool output are data. They must not be able to
close the evidence block, open a fake one, or break out of an attribute value.
"""

import re

_TAG = re.compile(r"<\s*(/?)\s*evidence", re.I)


def escape_body(text: str) -> str:
    """Neutralise any <evidence ...> / </evidence> lookalikes (any case or spacing)."""
    return _TAG.sub(lambda m: f"&lt;{m.group(1)}evidence", text)


def escape_attr(text: str, limit: int = 160) -> str:
    """Make text safe inside a double-quoted attribute: no quotes, angle brackets or newlines."""
    cleaned = (
        text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return " ".join(cleaned.split())[:limit]
