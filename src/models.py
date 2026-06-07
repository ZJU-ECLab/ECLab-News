from __future__ import annotations

import re
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
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .strip()
    )


_PSYCINFO_SUFFIX_RE = re.compile(
    r"\s*\(PsycInfo Database Record \(c\) \d{4} APA, all rights reserved\)\.?\s*$"
)
_ABSTRACT_PREFIX_RE = re.compile(r"(?i:Abstract)\s*[:\-]?\s*(?=[A-Z])")


def clean_abstract(value: object) -> str:
    text = clean_cell(value)
    text = _PSYCINFO_SUFFIX_RE.sub("", text)
    text = _ABSTRACT_PREFIX_RE.sub("", text)
    return text

