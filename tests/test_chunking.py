from vendorlens.services.chunking import (
    chunk_pages,
    normalize_text,
)
from vendorlens.services.pdf_parser import ParsedPage


def test_normalize_text():
    text = "Dell    offers\tthree years.\n\n\n\nWarranty applies."

    result = normalize_text(text)

    assert result == (
        "Dell offers three years.\n\nWarranty applies."
    )


def test_chunk_pages_preserves_page_number():
    pages = [
        ParsedPage(
            page_number=7,
            text="Dell provides a three year warranty.",
        )
    ]

    chunks = chunk_pages(pages)

    assert len(chunks) == 1
    assert chunks[0].page_number == 7
    assert chunks[0].chunk_index == 0
