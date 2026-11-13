"""Validate and extract text from uploaded files.

Supported: PDF (text layer only, page offsets preserved), Markdown, plain text.
Files are validated by content (magic bytes / UTF-8), not by extension alone.
"""

import io
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

ALLOWED_MIME = {
    "application/pdf": (".pdf",),
    "text/markdown": (".md", ".markdown"),
    "text/plain": (".txt", ".log"),
}
MAX_PDF_PAGES = 500


class UnsupportedDocument(ValueError):
    """Permanent failure: retrying will not help."""


@dataclass
class ParsedDocument:
    text: str
    is_markdown: bool
    # Character offset where each page starts (PDF only). page N (1-based) starts at [N-1].
    page_starts: list[int] = field(default_factory=list)

    def page_for(self, offset: int) -> int | None:
        if not self.page_starts:
            return None
        page = 1
        for i, start in enumerate(self.page_starts):
            if offset >= start:
                page = i + 1
        return page


def mime_allowed(mime_type: str, filename: str) -> bool:
    exts = ALLOWED_MIME.get(mime_type)
    return bool(exts) and filename.lower().endswith(exts)  # type: ignore[arg-type]


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def parse(data: bytes, mime_type: str) -> ParsedDocument:
    if mime_type == "application/pdf":
        return _parse_pdf(data)
    if mime_type in ("text/markdown", "text/plain"):
        if data[:5] == b"%PDF-":
            raise UnsupportedDocument("File content is a PDF but was declared as text")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise UnsupportedDocument("Text file is not valid UTF-8") from None
        text = _normalise(text)
        if not text:
            raise UnsupportedDocument("Document is empty")
        return ParsedDocument(text=text, is_markdown=mime_type == "text/markdown")
    raise UnsupportedDocument(f"Unsupported content type: {mime_type}")


def _parse_pdf(data: bytes) -> ParsedDocument:
    if data[:5] != b"%PDF-":
        raise UnsupportedDocument("File is not a valid PDF")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnsupportedDocument("Encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise UnsupportedDocument(f"PDF exceeds {MAX_PDF_PAGES} pages")
        parts: list[str] = []
        starts: list[int] = []
        offset = 0
        for page in reader.pages:
            page_text = _normalise(page.extract_text() or "")
            starts.append(offset)
            parts.append(page_text)
            offset += len(page_text) + 2  # "\n\n" separator
    except PdfReadError as e:
        raise UnsupportedDocument(f"Could not read PDF: {e}") from None
    text = "\n\n".join(parts)
    if not text.strip():
        raise UnsupportedDocument("PDF has no extractable text (scanned images are not supported)")
    return ParsedDocument(text=text, is_markdown=False, page_starts=starts)
