from __future__ import annotations

from dataclasses import asdict, dataclass


CSV_COLUMNS = [
    "title",
    "authors",
    "journal",
    "volume",
    "issue",
    "publish_date",
    "publish_info",
    "doi",
    "url",
    "abstract",
    "keywords",
    "matched_keywords",
    "category",
    "summary",
    "relevant",
    "recommended",
    "source",
    "source_id",
]


@dataclass
class Article:
    title: str = ""
    authors: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    publish_date: str = ""
    publish_info: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    keywords: str = ""
    matched_keywords: str = ""
    category: str = ""
    summary: str = ""
    relevant: str = ""
    recommended: str = ""
    source: str = ""
    source_id: str = ""

    def to_row(self) -> dict[str, str]:
        row = asdict(self)
        return {column: clean_cell(row.get(column, "")) for column in CSV_COLUMNS}


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return (
        text.replace("\r", " ")
        .replace("\n", " ")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .strip()
    )

