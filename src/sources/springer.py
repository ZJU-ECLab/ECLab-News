from __future__ import annotations

import os

import httpx

from ..models import Article, clean_abstract, clean_cell
from .common import doi_to_url, http_retry, join_people, publish_info

SPRINGER_META_URL = "https://api.springernature.com/meta/v2/json"


class SpringerClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("SPRINGER_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("SPRINGER_API_KEY environment variable is not set.")
        self.client = httpx.Client(timeout=30)

    def close(self) -> None:
        self.client.close()

    def fetch_by_doi(self, doi: str) -> Article | None:
        if not doi:
            return None
        try:
            data = self._get_json({"q": f"doi:{doi}", "api_key": self.api_key})
        except httpx.HTTPStatusError:
            return None
        records = data.get("records", [])
        if not records:
            return None
        return _to_article(records[0])

    @http_retry
    def _get_json(self, params: dict[str, str]) -> dict:
        response = self.client.get(SPRINGER_META_URL, params=params)
        response.raise_for_status()
        return response.json()


def _to_article(rec: dict) -> Article | None:
    title = clean_cell(rec.get("title", ""))
    if not title:
        return None

    abstract = clean_abstract(rec.get("abstract", ""))

    creators = rec.get("creators", [])
    names = []
    for c in creators:
        raw = c.get("creator", "")
        if ", " in raw:
            surname, given = raw.split(", ", 1)
            names.append(f"{given} {surname}")
        elif raw:
            names.append(raw)
    authors = join_people(names)

    keywords = clean_cell("; ".join(rec.get("keyword", []) or []))
    doi = clean_cell(rec.get("doi", ""))
    volume = clean_cell(rec.get("volume", ""))
    issue = clean_cell(rec.get("number", ""))
    pub_date = clean_cell(rec.get("publicationDate", ""))
    journal = clean_cell(rec.get("publicationName", ""))

    return Article(
        title=title,
        authors=authors,
        journal=journal,
        volume=volume,
        issue=issue,
        publish_date=pub_date,
        publish_info=publish_info(volume, issue, pub_date),
        doi=doi,
        url=doi_to_url(doi),
        abstract=abstract,
        keywords=keywords,
        source="springer",
        source_id=doi,
    )
