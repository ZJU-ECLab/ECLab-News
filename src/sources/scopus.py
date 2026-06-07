from __future__ import annotations

import os
import threading

from ..models import Article, clean_abstract, clean_cell
from .common import doi_to_url, join_people, publish_info

_init_lock = threading.Lock()
_initialized = False


def _ensure_init() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        import pybliometrics
        api_key = os.getenv("SCOPUS_API_KEY", "")
        if not api_key:
            raise RuntimeError("SCOPUS_API_KEY environment variable is not set.")
        pybliometrics.init(keys=[api_key])
        _initialized = True


class ScopusClient:
    def __init__(self) -> None:
        _ensure_init()

    def close(self) -> None:
        pass

    def fetch_by_doi(self, doi: str) -> Article | None:
        if not doi:
            return None
        article = _fetch_scopus(doi)
        if article:
            return article
        if doi.startswith("10.1016/"):
            return _fetch_sciencedirect(doi)
        return None


def _fetch_scopus(doi: str) -> Article | None:
    try:
        from pybliometrics.scopus import AbstractRetrieval
        ab = AbstractRetrieval(doi, id_type="doi", view="META_ABS")
    except Exception:
        return None
    abstract = clean_abstract(ab.abstract or ab.description or "")
    if not abstract:
        return None
    return _scopus_to_article(ab, abstract)


def _fetch_sciencedirect(doi: str) -> Article | None:
    try:
        from pybliometrics.sciencedirect import ArticleRetrieval
        ar = ArticleRetrieval(doi, id_type="doi", view="META_ABS")
    except Exception:
        return None
    abstract = clean_abstract(ar.abstract or "")
    if not abstract:
        return None
    return _sciencedirect_to_article(ar, abstract)


def _scopus_to_article(ab, abstract: str) -> Article | None:
    title = clean_cell(ab.title or "")
    if not title:
        return None

    authors_raw = ab.authors or []
    names = []
    for a in authors_raw:
        parts = [p for p in [a.given_name, a.surname] if p]
        if parts:
            names.append(" ".join(parts))
    authors = join_people(names)

    keywords = clean_cell("; ".join(ab.authkeywords or []))
    doi = clean_cell(ab.doi or "")
    volume = clean_cell(ab.volume or "")
    issue = clean_cell(ab.issueIdentifier or "")
    pub_date = clean_cell(ab.coverDate or "")
    journal = clean_cell(ab.publicationName or "")
    eid = clean_cell(ab.eid or "")

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
        source="scopus",
        source_id=eid,
    )


def _sciencedirect_to_article(ar, abstract: str) -> Article | None:
    title = clean_cell(ar.title or "")
    if not title:
        return None

    authors_raw = ar.authors or []
    names = []
    for a in authors_raw:
        parts = [p for p in [a.given_name, a.surname] if p]
        if parts:
            names.append(" ".join(parts))
    authors = join_people(names)

    doi = clean_cell(ar.doi or "")
    pub_date = clean_cell(ar.coverDate or "")
    journal = clean_cell(ar.publicationName or "")
    eid = clean_cell(ar.eid or "")
    volume = clean_cell(str(ar.volume or ""))

    return Article(
        title=title,
        authors=authors,
        journal=journal,
        volume=volume,
        publish_date=pub_date,
        publish_info=publish_info(volume, "", pub_date),
        doi=doi,
        url=doi_to_url(doi),
        abstract=abstract,
        source="scopus",
        source_id=eid,
    )
