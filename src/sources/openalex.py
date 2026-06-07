from __future__ import annotations

from urllib.parse import quote

import httpx

from ..models import Article, clean_abstract, clean_cell
from .common import doi_to_url, http_retry, join_people, publish_info

OPENALEX_WORK_URL = "https://api.openalex.org/works/{doi_url}"
OPENALEX_SEARCH_URL = "https://api.openalex.org/works"




class OpenAlexClient:
    def __init__(self, email: str = "") -> None:
        self.email = email
        self.client = httpx.Client(
            timeout=45,
            headers={"Accept": "application/json", "User-Agent": _user_agent(email)},
        )

    def close(self) -> None:
        self.client.close()

    def fetch_by_doi(self, doi: str) -> Article | None:
        if not doi:
            return None
        doi_url = doi_to_url(doi)
        params = {"mailto": self.email} if self.email else {}
        try:
            payload = self._get_json(OPENALEX_WORK_URL.format(doi_url=quote(doi_url, safe="")), params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return _payload_to_article(payload)

    def fetch_by_title(self, title: str) -> Article | None:
        """Title-based search fallback for when DOI lookup has no abstract."""
        if not title:
            return None
        params = {"search": title, "per-page": "1"}
        if self.email:
            params["mailto"] = self.email
        try:
            data = self._get_json(OPENALEX_SEARCH_URL, params)
        except httpx.HTTPError:
            return None
        results = data.get("results", [])
        if not results:
            return None
        return _payload_to_article(results[0])

    @http_retry
    def _get_json(self, url: str, params: dict[str, str]) -> dict:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _payload_to_article(payload: dict) -> Article:
    source = payload.get("primary_location", {}).get("source") or {}
    biblio = payload.get("biblio") or {}
    doi = clean_cell(str(payload.get("doi", "")).removeprefix("https://doi.org/"))
    volume = clean_cell(biblio.get("volume", ""))
    issue = clean_cell(biblio.get("issue", ""))
    publish_date = clean_cell(payload.get("publication_date", ""))
    return Article(
        title=clean_cell(payload.get("title", "")),
        authors=join_people(
            [
                clean_cell(author.get("author", {}).get("display_name", ""))
                for author in payload.get("authorships", [])
            ]
        ),
        journal=clean_cell(source.get("display_name", "")),
        volume=volume,
        issue=issue,
        publish_date=publish_date,
        publish_info=publish_info(volume, issue, publish_date),
        doi=doi,
        url=doi_to_url(doi) or clean_cell(payload.get("id", "")),
        abstract=clean_abstract(_abstract_from_inverted_index(payload.get("abstract_inverted_index"))),
        keywords=clean_cell("; ".join(_concept_names(payload))),
        source="openalex",
        source_id=clean_cell(payload.get("id", "")),
    )


def _abstract_from_inverted_index(index: dict | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((int(position), str(word)))
    return " ".join(word for _, word in sorted(words))


def _concept_names(payload: dict) -> list[str]:
    concepts = payload.get("concepts") or []
    keywords = payload.get("keywords") or []
    names = [concept.get("display_name", "") for concept in concepts[:8]]
    names.extend(keyword.get("display_name", "") for keyword in keywords[:8])
    seen: set[str] = set()
    unique = []
    for name in names:
        cleaned = clean_cell(name)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique.append(cleaned)
    return unique


def _user_agent(email: str) -> str:
    if email:
        return f"eclab-news/0.1 (mailto:{email})"
    return "eclab-news/0.1"

