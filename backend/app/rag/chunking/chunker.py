"""Structure-aware chunking.

- Markdown headings define sections; each chunk records its heading path and the
  path is kept with the content so retrieval sees the context.
- Fenced code blocks and log blocks (consecutive timestamped lines) are atomic
  unless a single block is larger than the hard limit.
- Blocks are packed up to ~target tokens with ~overlap tokens carried forward.
- Token counts are estimated (~4 chars/token); this is an approximation and is
  only used for sizing, never for billing.
"""

import hashlib
import re
from dataclasses import dataclass

from app.rag.ingestion.parsers import ParsedDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^(```|~~~)")
_LOG_LINE = re.compile(r"^\s*(\[?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|[A-Z]+\s+\|)")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Block:
    text: str
    start: int
    end: int
    section: tuple[str, ...]
    atomic: bool = False


@dataclass
class Chunk:
    index: int
    content: str
    section_path: str | None
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    token_estimate: int
    content_hash: str


def _blocks(text: str, markdown: bool) -> list[Block]:
    """Split into paragraphs / fenced blocks / log blocks with char offsets."""
    blocks: list[Block] = []
    section: list[tuple[int, str]] = []
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    i = 0
    buf_start: int | None = None
    buf_kind = ""

    def path() -> tuple[str, ...]:
        return tuple(t for _, t in section)

    def flush(end_line: int) -> None:
        nonlocal buf_start, buf_kind
        if buf_start is None:
            return
        start = offsets[buf_start]
        end = offsets[end_line - 1] + len(lines[end_line - 1])
        chunk_text = text[start:end].strip("\n")
        if chunk_text.strip():
            blocks.append(Block(chunk_text, start, end, path(), atomic=buf_kind in ("code", "log")))
        buf_start, buf_kind = None, ""

    while i < len(lines):
        line = lines[i]
        if markdown and _FENCE.match(line):
            flush(i)
            fence = line[:3]
            j = i + 1
            while j < len(lines) and not lines[j].startswith(fence):
                j += 1
            j = min(j + 1, len(lines))
            buf_start, buf_kind = i, "code"
            flush(j)
            i = j
            continue
        m = _HEADING.match(line) if markdown else None
        if m:
            flush(i)
            level = len(m.group(1))
            section = [(lvl, t) for lvl, t in section if lvl < level] + [(level, m.group(2))]
            i += 1
            continue
        if not line.strip():
            flush(i)
            i += 1
            continue
        kind = "log" if _LOG_LINE.match(line) else "text"
        if buf_start is not None and kind != buf_kind and "log" in (kind, buf_kind):
            flush(i)
        if buf_start is None:
            buf_start, buf_kind = i, kind
        i += 1
    flush(len(lines))
    return blocks


def _split_oversized(block: Block, hard_limit: int) -> list[Block]:
    if estimate_tokens(block.text) <= hard_limit:
        return [block]
    out: list[Block] = []
    cur: list[str] = []
    cur_start = block.start
    pos = block.start
    for line in block.text.split("\n"):
        if cur and estimate_tokens("\n".join([*cur, line])) > hard_limit:
            piece = "\n".join(cur)
            out.append(Block(piece, cur_start, cur_start + len(piece), block.section, False))
            cur, cur_start = [], pos
        cur.append(line)
        pos += len(line) + 1
    if cur:
        piece = "\n".join(cur)
        out.append(Block(piece, cur_start, cur_start + len(piece), block.section, False))
    return out


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _overlap_tail(blocks: list[Block], overlap_tokens: int) -> list[Block]:
    """Trailing context (whole blocks, else trailing sentences) to repeat in the next chunk."""
    carry: list[Block] = []
    budget = overlap_tokens
    for b in reversed(blocks):
        if b.atomic:
            break
        size = estimate_tokens(b.text)
        if size <= budget:
            carry.insert(0, b)
            budget -= size
            continue
        # take trailing sentences of this block that fit in the remaining budget
        sentences = _SENTENCE_END.split(b.text)
        tail: list[str] = []
        for sent in reversed(sentences):
            if estimate_tokens(" ".join([sent, *tail])) > budget:
                break
            tail.insert(0, sent)
        if tail:
            piece = " ".join(tail)
            idx = b.text.rfind(tail[0])
            start = b.start + max(idx, 0)
            carry.insert(0, Block(piece, start, b.end, b.section, False))
        break
    return carry


def chunk_document(
    doc: ParsedDocument, target_tokens: int = 500, overlap_tokens: int = 80
) -> list[Chunk]:
    hard_limit = target_tokens * 2
    blocks: list[Block] = []
    for b in _blocks(doc.text, doc.is_markdown):
        blocks.extend(_split_oversized(b, hard_limit))

    chunks: list[Chunk] = []
    current: list[Block] = []

    def emit() -> None:
        if not current:
            return
        section = current[-1].section
        section_path = " > ".join(section) if section else None
        body = "\n\n".join(b.text for b in current)
        content = f"{section_path}\n\n{body}" if section_path else body
        start, end = current[0].start, current[-1].end
        chunks.append(
            Chunk(
                index=len(chunks),
                content=content,
                section_path=section_path,
                char_start=start,
                char_end=end,
                page_start=doc.page_for(start),
                page_end=doc.page_for(max(start, end - 1)),
                token_estimate=estimate_tokens(content),
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
            )
        )

    for block in blocks:
        size = sum(estimate_tokens(b.text) for b in current)
        new_section = bool(current) and block.section != current[-1].section
        if current and (new_section or size + estimate_tokens(block.text) > target_tokens):
            emit()
            if new_section:
                current = []
            else:
                # carry trailing non-atomic blocks as overlap
                current = _overlap_tail(current, overlap_tokens)
        current.append(block)
    emit()
    return chunks
