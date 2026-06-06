from __future__ import annotations

import os

import httpx

from ..models import Article, clean_cell
from .common import doi_to_url, join_people, publish_info, http_retry

SCOPUS_ABSTRACT_URL = "https://api.elsevier.com/content/abstract/doi/{doi}"




class ScopusClient:
    def __init__(self) -> None:
        api_key = os.getenv("SCOPUS_API_KEY", "")
        if not api_key:
            raise RuntimeError("SCOPUS_API_KEY environment variable is not set.")
        self.client = httpx.Client(
            timeout=45,
            headers={"Accept": "application/json", "X-ELS-APIKey": api_key},
        )

    def close(self) -> None:
        self.client.close()

    def fetch_by_doi(self, doi: str) -> Article | None:
        if not doi:
            return None
        try:
            payload = self._get_json(SCOPUS_ABSTRACT_URL.format(doi=doi))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 401, 403, 404):
                return None
            raise
        return _payload_to_article(payload)

    @http_retry
    def _get_json(self, url: str) -> dict:
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()


def _payload_to_article(payload: dict) -> Article:
    core = payload.get("abstracts-retrieval-response", {})
    item = core.get("item", {})
    bibrecord = item.get("bibrecord", {})
    head = bibrecord.get("head", {})
    citation_info = head.get("citation-info", {})
    source = head.get("source", {})

    title = clean_cell(
        (head.get("citation-title") or "")
        or _nested(core, "coredata", "dc:title", default="")
    )
    abstract = clean_cell(
        _nested(core, "coredata", "dc:description", default="")
        or str(head.get("abstracts") or "")
    )

    authors_raw = head.get("author-group") or []
    if isinstance(authors_raw, dict):
        authors_raw = [authors_raw]
    names: list[str] = []
    for group in authors_raw:
        for author in _as_list(group.get("author") or []):
            given = clean_cell(str(author.get("ce:given-name", "") or ""))
            surname = clean_cell(str(author.get("ce:surname", "") or ""))
            names.append(" ".join(p for p in [given, surname] if p))
    authors = join_people(names)

    keywords_raw = _nested(core, "authkeywords", "author-keyword", default=[])
    if isinstance(keywords_raw, dict):
        keywords_raw = [keywords_raw]
    keywords = clean_cell("; ".join(
        str(kw.get("$", "") if isinstance(kw, dict) else kw)
        for kw in _as_list(keywords_raw)
    ))

    doi = clean_cell(_nested(core, "coredata", "prism:doi", default=""))
    volume = clean_cell(str(source.get("volisspag", {}).get("voliss", {}).get("@volume", "") or ""))
    issue = clean_cell(str(source.get("volisspag", {}).get("voliss", {}).get("@issue", "") or ""))
    pub_date = clean_cell(_nested(core, "coredata", "prism:coverDate", default=""))
    journal_name = clean_cell(str(source.get("sourcetitle", "") or ""))
    eid = clean_cell(_nested(core, "coredata", "eid", default=""))

    return Article(
        title=title,
        authors=authors,
        journal=journal_name,
        volume=volume,
        issue=issue,
        publish_date=pub_date,
        publish_info=publish_info(volume, issue, pub_date),
        doi=doi,
        url=doi_to_url(doi),
        abstract=abstract,
        keywords=keywords,
        source="scopus",
        source_id=eid,
    )


def _nested(d: dict, *keys: str, default: object = "") -> object:
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, {})
    return d if d != {} else default


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []
