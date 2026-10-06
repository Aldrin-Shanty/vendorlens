import re
from dataclasses import dataclass

from vendorlens.services.pdf_parser import ParsedPage


@dataclass
class TextChunk:
    page_number: int
    chunk_index: int
    text: str


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def chunk_pages(
    pages: list[ParsedPage],
    chunk_size: int = 300,
    overlap: int = 50,
) -> list[TextChunk]:
    chunks = []

    for page in pages:
        text = normalize_text(page.text)

        if not text:
            continue

        words = text.split()

        start = 0
        chunk_index = 0

        while start < len(words):
            end = start + chunk_size

            chunk_text = " ".join(
                words[start:end]
            )

            chunks.append(
                TextChunk(
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    text=chunk_text,
                )
            )

            chunk_index += 1

            if end >= len(words):
                break

            start = end - overlap

    return chunks
