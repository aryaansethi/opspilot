"""Escaping for untrusted text placed inside <evidence> blocks in LLM prompts.

Retrieved documents, log lines and tool output are data. They must not be able to
close the evidence block, open a fake one, or break out of an attribute value.
"""

import re

_TAG = re.compile(r"<\s*(/?)\s*evidence", re.I)
# Lines in retrieved documents / logs / tool output that address an AI system rather than describe
# the system being investigated. They are removed (visibly) before the model sees the text.
_INSTRUCTION_LIKE = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
    r"|\byou\s+are\s+now\b"
    r"|^\s*(system|assistant)\s*:"
    r"|\b(administrator|admin|developer)\s+mode\b"
    r"|\bnote\s+to\s+(ai|llm|language\s+model|assistants?)\b"
    r"|\b(print|reveal|show|repeat)\s+(your\s+)?(full\s+)?(system\s+prompt|instructions)\b"
    r"|\b(regardless\s+of|ignore)\s+the\s+(user'?s\s+)?question\b"
    r"|<\s*/?\s*evidence\b",
    re.I | re.M,
)
REMOVED_NOTE = "[OpsPilot removed a line that looked like instructions to an AI system]"


def sanitize_untrusted(text: str) -> tuple[str, int]:
    """Replace instruction-like lines; returns (text, number of lines removed)."""
    out, removed = [], 0
    for line in text.split("\n"):
        if _INSTRUCTION_LIKE.search(line):
            out.append(REMOVED_NOTE)
            removed += 1
        else:
            out.append(line)
    return "\n".join(out), removed


def escape_body(text: str) -> str:
    """Remove instruction-like lines, then neutralise any remaining <evidence> lookalikes."""
    cleaned, _ = sanitize_untrusted(text)
    return _TAG.sub(lambda m: f"&lt;{m.group(1)}evidence", cleaned)


def escape_attr(text: str, limit: int = 160) -> str:
    """Make text safe inside a double-quoted attribute: no quotes, angle brackets or newlines."""
    cleaned = (
        text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return " ".join(cleaned.split())[:limit]
