"""Read and normalize source data. TODO: implement functions."""
from pathlib import Path
from .models import DocumentPage
import re
import unicodedata
from typing import Any
from pypdf import PdfReader



def load_pdf(path: Path, document_id: str, source: str, metadata:dict | None = None,) -> list[DocumentPage]:
    """TODO: extract each physical page; keep its page number and source.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    if not path.is_file():
        raise ValueError(f"Expected a PDF file: {path}")

    reader = PdfReader(str(path))

    pages = []

    for page_number, pdf_page in enumerate(reader.pages, start=1):
        extraction_error = None

        try:
            raw_text = pdf_page.extract_text() or ""
        except Exception as error:
            raw_text = ""
            extraction_error = (
                f"{type(error).__name__}: {error}"
            )
        text = normalize_text(raw_text)

        page_metadata = dict(metadata or {})

        page_metadata.update({
            "physical_page_number": page_number,
            "character_count": len(text),
            "has_text": bool(text),
            "low_text": len(text) < 200,
            "extraction_status": (
                "error" if extraction_error
                else "ok" if text
                else "no_text"
            ),
        })

        if extraction_error:
            page_metadata["extraction_error"] = extraction_error

        document_page = DocumentPage(
            document_id=document_id,
            source=source,
            page=page_number,
            text=text,
            metadata=page_metadata,
        )

        pages.append(document_page)
    return pages


def normalize_text(text: str) -> str:
    """TODO: normalize Unicode and whitespace without discarding useful structure."""
    if not text:
        return ""

    # Normalize unicode characters
    text = unicodedata.normalize("NFC", text)
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove invisible formatting characters
    text = text.replace("\u200b", "")
    text = text.replace("\u00ad", "")
    # Normalize non-breaking spaces
    text = text.replace("\u00a0", " ")

    # Normalize spaces while perserving line breaks
    lines = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+"," ", line).strip()
        lines.append(line)

    # Keep at most one blank line between paragraphs
    normalized_lines = []
    previous_blank = False

    for line in lines:
        if not line:
            if normalized_lines and not previous_blank:
                normalized_lines.append("")
            previous_blank = True
        else:
            normalized_lines.append(line)
            previous_blank = False
    return "\n".join(normalized_lines).strip()
