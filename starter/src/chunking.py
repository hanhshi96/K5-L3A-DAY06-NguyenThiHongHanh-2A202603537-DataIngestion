
"""Fixed-size and structure-aware token-aware chunking."""

from .models import Chunk, DocumentPage
import hashlib
import re
from typing import Any


def _make_chunk(
    page: DocumentPage,
    text: str,
    strategy: str,
    start: int,
    end: int,
    extra_metadata: dict | None = None,
) -> Chunk:
    """Create a stable chunk ID and preserve source traceability."""

    metadata = dict(page.metadata)

    metadata.update({
        "chunking_strategy": strategy,
        "start_char": start,
        "end_char": end,
        "chunk_length": len(text),
    })

    if extra_metadata:
        metadata.update(extra_metadata)

    identity = (
        f"{page.document_id}|{page.page}|"
        f"{strategy}|{start}|{end}|{text}"
    )

    chunk_hash = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16]

    chunk_id = (
        f"{page.document_id}-p{page.page:04d}-"
        f"{strategy}-{chunk_hash}"
    )

    return Chunk(
        chunk_id=chunk_id,
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=metadata,
    )


def _count_tokens(tokenizer: Any, text: str) -> int:
    """Count tokens including special tokens."""

    return len(
        tokenizer.encode(
            text,
            add_special_tokens=True,
            truncation=False,
        )
    )


def _split_by_token_limit(
    text: str,
    tokenizer: Any,
    max_tokens: int,
) -> list[tuple[int, int, str, int]]:
    """Split text using tokenizer offsets.

    Returns:
        (start_char, end_char, text, token_count)

    Every returned text is verified against max_tokens.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")

    if not text.strip():
        return []

    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
    )

    offsets = [
        (int(start), int(end))
        for start, end in encoded["offset_mapping"]
        if end > start
    ]

    if not offsets:
        return []

    pieces = []
    token_start = 0
    char_start = 0

    while token_start < len(offsets):

        token_end = min(
            token_start + max_tokens,
            len(offsets),
        )

        selected = None

        while token_end > token_start:

            if token_end < len(offsets):
                char_end = offsets[token_end][0]
            else:
                char_end = len(text)

            if char_end <= char_start:
                token_end -= 1
                continue

            candidate = text[char_start:char_end]

            token_count = _count_tokens(
                tokenizer,
                candidate,
            )

            if token_count <= max_tokens:
                selected = (char_end, candidate, token_count)
                break

            token_end -= 1

        if selected is None:
            raise RuntimeError(
                "Unable to split text within token limit."
            )

        char_end, candidate, token_count = selected

        leading = len(candidate) - len(candidate.lstrip())
        actual_start = char_start + leading

        actual_end = (
            char_start + len(candidate.rstrip())
        )

        piece_text = text[actual_start:actual_end]

        if piece_text:
            actual_count = _count_tokens(
                tokenizer,
                piece_text,
            )

            if actual_count > max_tokens:
                raise RuntimeError(
                    "Generated chunk exceeds token limit."
                )

            pieces.append((
                actual_start,
                actual_end,
                piece_text,
                actual_count,
            ))

        char_start = char_end
        token_start = token_end

    return pieces


def fixed_size(
    page: DocumentPage,
    size: int,
    overlap: int,
    tokenizer: Any | None = None,
    max_tokens: int = 240,
) -> list[Chunk]:
    """Split into fixed-size windows and optionally enforce token limit."""

    if size <= 0:
        raise ValueError("size must be greater than zero")

    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >=0 and < size")

    text = page.text

    if not text.strip():
        return []

    chunks = []
    start = 0
    step = size - overlap

    while start < len(text):

        end = min(start + size, len(text))
        raw_text = text[start:end]

        leading = len(raw_text) - len(raw_text.lstrip())
        actual_start = start + leading
        actual_end = start + len(raw_text.rstrip())

        chunk_text = raw_text.strip()

        if chunk_text:

            if tokenizer is None:
                chunks.append(
                    _make_chunk(
                        page=page,
                        text=chunk_text,
                        strategy="fixed",
                        start=actual_start,
                        end=actual_end,
                    )
                )

            else:
                pieces = _split_by_token_limit(
                    chunk_text,
                    tokenizer,
                    max_tokens,
                )

                for part_start, part_end, part_text, count in pieces:
                    chunks.append(
                        _make_chunk(
                            page=page,
                            text=part_text,
                            strategy="fixed",
                            start=actual_start + part_start,
                            end=actual_start + part_end,
                            extra_metadata={
                                "token_count": count,
                                "token_limit": max_tokens,
                                "token_split": len(pieces) > 1,
                            },
                        )
                    )

        if end == len(text):
            break

        start += step

    return chunks


def _split_oversized_paragraph(
    text: str,
    start: int,
    end: int,
    max_size: int,
) -> list[tuple[int, int]]:
    """Split oversized paragraphs near whitespace boundaries."""

    segments = []
    position = start

    while position < end:

        limit = min(position + max_size, end)

        if limit < end:
            candidates = [
                text.rfind(" ", position, limit),
                text.rfind("\n", position, limit),
                text.rfind("\t", position, limit),
            ]

            boundary = max(candidates)

            if boundary > position + max_size // 2:
                limit = boundary

        if limit <= position:
            limit = min(position + max_size, end)

        segment_start = position
        segment_end = limit

        while (
            segment_start < segment_end
            and text[segment_start].isspace()
        ):
            segment_start += 1

        while (
            segment_end > segment_start
            and text[segment_end - 1].isspace()
        ):
            segment_end -= 1

        if segment_start < segment_end:
            segments.append((segment_start, segment_end))

        position = limit

        while position < end and text[position].isspace():
            position += 1

    return segments


def by_paragraph(
    page: DocumentPage,
    max_size: int,
    tokenizer: Any | None = None,
    max_tokens: int = 240,
) -> list[Chunk]:
    """Group paragraphs and enforce optional token limit."""

    if max_size <= 0:
        raise ValueError("max_size must be greater than zero")

    text = page.text

    if not text.strip():
        return []

    paragraph_pattern = re.compile(
        r"\S.*?(?=\n[ \t]*\n|\Z)",
        re.DOTALL,
    )

    segments = []

    for paragraph_index, match in enumerate(
        paragraph_pattern.finditer(text)
    ):

        start = match.start()
        end = match.end()

        while end > start and text[end - 1].isspace():
            end -= 1

        if start >= end:
            continue

        if end - start <= max_size:

            segments.append({
                "start": start,
                "end": end,
                "paragraph_index": paragraph_index,
            })

        else:

            parts = _split_oversized_paragraph(
                text,
                start,
                end,
                max_size,
            )

            for part_index, (part_start, part_end) in enumerate(parts):

                segments.append({
                    "start": part_start,
                    "end": part_end,
                    "paragraph_index": paragraph_index,
                    "part_index": part_index,
                })

    # Merge adjacent paragraphs while respecting max_size.
    groups = []

    for segment in segments:

        if (
            groups
            and segment["end"] - groups[-1]["start"] <= max_size
        ):

            groups[-1]["end"] = segment["end"]

            groups[-1]["paragraph_indices"].append(
                segment["paragraph_index"]
            )

        else:

            groups.append({
                "start": segment["start"],
                "end": segment["end"],
                "paragraph_indices": [
                    segment["paragraph_index"]
                ],
            })

    chunks = []

    for group in groups:

        start = group["start"]
        end = group["end"]

        raw_text = text[start:end]

        leading = len(raw_text) - len(raw_text.lstrip())
        actual_start = start + leading
        actual_end = start + len(raw_text.rstrip())

        chunk_text = text[actual_start:actual_end]

        if not chunk_text:
            continue

        # Remove standalone printed page-number artifacts.
        if chunk_text.isdigit():
            printed_page = int(chunk_text)

            if printed_page in {page.page, page.page - 1}:
                continue

        paragraph_metadata = {
            "paragraph_indices": group["paragraph_indices"],
            "paragraph_count": len(group["paragraph_indices"]),
        }

        if tokenizer is None:

            chunks.append(
                _make_chunk(
                    page=page,
                    text=chunk_text,
                    strategy="paragraph",
                    start=actual_start,
                    end=actual_end,
                    extra_metadata=paragraph_metadata,
                )
            )

        else:

            pieces = _split_by_token_limit(
                chunk_text,
                tokenizer,
                max_tokens,
            )

            for part_start, part_end, part_text, count in pieces:

                extra_metadata = {
                    **paragraph_metadata,
                    "token_count": count,
                    "token_limit": max_tokens,
                    "token_split": len(pieces) > 1,
                }

                chunks.append(
                    _make_chunk(
                        page=page,
                        text=part_text,
                        strategy="paragraph",
                        start=actual_start + part_start,
                        end=actual_start + part_end,
                        extra_metadata=extra_metadata,
                    )
                )

    return chunks
