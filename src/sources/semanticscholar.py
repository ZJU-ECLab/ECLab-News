from __future__ import annotations

import os

import httpx

from ..models import Article, clean_abstract, clean_cell
from .common import doi_to_url, join_people, publish_info, http_retry

S2_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
S2_FIELDS = "title,authors,year,journal,externalIds,abstract,fieldsOfStudy,publicationDate,volume,venue"




class SemanticScholarClient:
    def __init__(self) -> None:
        api_key = os.getenv("S2_API_KEY", "")
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        self.client = httpx.Client(timeout=45, headers=headers)

    def close(self) -> None:
        self.client.close()

    def fetch_by_doi(self, doi: str) -> Article | None:
        if not doi:
            return None
        try:
            payload = self._get_json(S2_PAPER_URL.format(doi=doi), {"fields": S2_FIELDS})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 400):
                return None
            raise
        return _payload_to_article(payload)

    @http_retry
    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _payload_to_article(payload: dict) -> Article:
    journal = payload.get("journal") or {}
    doi = clean_cell(str((payload.get("externalIds") or {}).get("DOI", "")))
    volume = clean_cell(str(journal.get("volume", "") or ""))
    pub_date = clean_cell(payload.get("publicationDate", "") or str(payload.get("year", "") or ""))
    authors = join_people(
        [clean_cell(a.get("name", "")) for a in (payload.get("authors") or [])]
    )
    journal_name = clean_cell(journal.get("name", "") or payload.get("venue", ""))
    return Article(
        title=clean_cell(payload.get("title", "")),
        authors=authors,
        journal=journal_name,
        volume=volume,
        publish_date=pub_date,
        publish_info=publish_info(volume, "", pub_date),
        doi=doi,
        url=doi_to_url(doi),
        abstract=clean_abstract(payload.get("abstract", "") or ""),
        keywords=clean_cell("; ".join(payload.get("fieldsOfStudy") or [])),
        source="semanticscholar",
        source_id=clean_cell(payload.get("paperId", "")),
    )
