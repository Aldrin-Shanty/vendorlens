from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class ParsedPage:
    page_number: int
    text: str


def parse_pdf(path: Path) -> list[ParsedPage]:
    reader = PdfReader(path)

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = page.extract_text() or ""

        pages.append(
            ParsedPage(
                page_number=page_number,
                text=text,
            )
        )

    return pages
