import pytest

from app.rag.chunking.chunker import chunk_document, estimate_tokens
from app.rag.ingestion.parsers import ParsedDocument, UnsupportedDocument, mime_allowed, parse

RUNBOOK = """# Orders API Runbook

Intro paragraph about the orders service.

## Database connection exhaustion

Symptoms: p95 latency rises and `HikariPool-1 - Connection is not available` errors appear.

```bash
kubectl -n orders exec deploy/orders-api -- curl localhost:8080/actuator/metrics/hikaricp.connections.active
```

2026-11-02T10:01:02Z ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms
2026-11-02T10:01:03Z ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms

## Rollback

Use the deploy pipeline to roll back to the previous release.
"""


def test_markdown_sections_are_kept_with_content() -> None:
    chunks = chunk_document(parse(RUNBOOK.encode(), "text/markdown"), target_tokens=60)
    paths = [c.section_path for c in chunks]
    assert "Orders API Runbook > Database connection exhaustion" in paths
    assert "Orders API Runbook > Rollback" in paths
    for c in chunks:
        if c.section_path:
            assert c.content.startswith(c.section_path)


def test_code_and_log_blocks_are_not_split() -> None:
    chunks = chunk_document(parse(RUNBOOK.encode(), "text/markdown"), target_tokens=40)
    joined = [c.content for c in chunks]
    assert any("```bash" in c and "hikaricp.connections.active\n```" in c for c in joined)
    log_chunks = [c for c in joined if "request timed out" in c]
    assert all(c.count("HikariPool-1") >= 2 for c in log_chunks if "2026-11-02" in c)


def test_offsets_point_back_into_source() -> None:
    doc = parse(RUNBOOK.encode(), "text/markdown")
    for c in chunk_document(doc, target_tokens=60):
        assert 0 <= c.char_start < c.char_end <= len(doc.text)
        assert c.content_hash and c.token_estimate > 0


def test_overlap_and_size_bound_on_long_text() -> None:
    para = "The connection pool limit was reduced from 50 to 10 in release 4.2. " * 6
    text = "\n\n".join(f"Paragraph {i}. {para}" for i in range(30))
    chunks = chunk_document(ParsedDocument(text=text, is_markdown=False), 200, 60)
    assert len(chunks) > 5
    assert all(c.token_estimate <= 200 * 2 for c in chunks)
    # consecutive chunks share an overlapping paragraph
    assert any(chunks[i].char_end > chunks[i + 1].char_start for i in range(len(chunks) - 1))


def test_pdf_page_mapping() -> None:
    doc = ParsedDocument(
        text="page one text\n\npage two text", is_markdown=False, page_starts=[0, 15]
    )
    assert doc.page_for(3) == 1 and doc.page_for(20) == 2


def test_parser_validation() -> None:
    assert mime_allowed("application/pdf", "a.PDF")
    assert not mime_allowed("application/pdf", "a.exe")
    assert not mime_allowed("application/zip", "a.zip")
    with pytest.raises(UnsupportedDocument):
        parse(b"not a pdf", "application/pdf")
    with pytest.raises(UnsupportedDocument):
        parse(b"\xff\xfe\x00bad", "text/plain")
    with pytest.raises(UnsupportedDocument):
        parse(b"   \n ", "text/plain")
    assert estimate_tokens("abcd" * 10) == 10
