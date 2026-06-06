from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
import re
import threading
from typing import Any

import httpx
from tenacity import retry_if_exception, stop_after_attempt, wait_exponential

from ..category import infer_categories
from ..config import AppConfig
from ..journals import article_matches_configured_journal, issns_for_journal, looks_supplemental
from ..models import Article, clean_cell
from .common import date_in_range, doi_to_url, http_retry, join_people, matched_terms, publish_info

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
_SEARCH_WORKERS = 10


class CrossrefClient:
    def __init__(self, email: str = "") -> None:
        self.email = email
        self._headers = {
            "Accept": "application/json",
            "User-Agent": _user_agent(email),
        }
        self.client = httpx.Client(timeout=45, headers=self._headers)

    def close(self) -> None:
        self.client.close()

    def search(self, config: AppConfig, start: date, end: date, max_results: int = 500) -> list[Article]:
        # One task per journal — fetch all articles in the date range, filter locally
        tasks: list[tuple[str, list[str]]] = []
        for journal in config.search.journals or [""]:
            issns = issns_for_journal(journal, config.search.journal_issns) or [""]
            tasks.append((journal, issns))

        articles: list[Article] = []
        seen: set[str] = set()
        lock = threading.Lock()
        counter = [0]

        def _fetch(task: tuple[str, list[str]]) -> list[Article]:
            journal, issns = task
            client = httpx.Client(timeout=45, headers=self._headers)
            try:
                items = _search_page(client, self.email, "", journal, issns, start, end, rows=100)
                result = []
                for item in items:
                    article = self._item_to_article(item, config, start, end)
                    if article is not None:
                        result.append(article)
                return result
            except Exception:
                return []
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=_SEARCH_WORKERS) as pool:
            futures = {pool.submit(_fetch, t): t for t in tasks}
            for future in as_completed(futures):
                batch = future.result()
                with lock:
                    for article in batch:
                        if len(articles) >= max_results:
                            break
                        key = article.doi.lower() or article.title.lower()
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        articles.append(article)
                        counter[0] += 1
                        print(f"\rCollecting Crossref: {counter[0]} articles", end="", flush=True)
        print()
        return articles

    def _item_to_article(
        self,
        item: dict[str, Any],
        config: AppConfig,
        start: date,
        end: date,
    ) -> Article | None:
        title = clean_cell(_first(item.get("title", [])))
        journal = clean_cell(_first(item.get("container-title", [])))
        article_issns = [clean_cell(issn) for issn in item.get("ISSN", [])]
        if not article_matches_configured_journal(
            journal,
            article_issns,
            config.search.journals,
            config.search.journal_issns,
        ):
            return None
        doi = clean_cell(item.get("DOI", ""))
        if config.search.exclude_supplemental and looks_supplemental(title, doi):
            return None
        publish_date = _published_date(item)
        if not date_in_range(publish_date, start, end):
            return None

        abstract = clean_cell(_strip_crossref_abstract(item.get("abstract", "")))
        keywords = clean_cell("; ".join(item.get("subject", []) or []))
        volume = clean_cell(item.get("volume", ""))
        issue = clean_cell(item.get("issue", ""))
        matched = matched_terms(title, abstract, keywords, config.search.keywords)
        category = infer_categories(title, abstract, keywords, matched, config.categories)
        authors = join_people([_author_name(author) for author in item.get("author", []) or []])

        return Article(
            title=title,
            authors=authors,
            journal=journal,
            volume=volume,
            issue=issue,
            publish_date=publish_date,
            publish_info=publish_info(volume, issue, publish_date),
            doi=doi,
            url=doi_to_url(doi) or clean_cell(item.get("URL", "")),
            abstract=abstract,
            keywords=keywords,
            matched_keywords=matched,
            category=category or matched,
            source="crossref",
            source_id=doi,
        )

    def _enrich_missing(self, article: Article) -> Article:
        if not article.doi:
            return article
        if article.abstract and article.keywords and article.authors:
            return article
        try:
            payload = self._get_json(f"{CROSSREF_WORKS_URL}/{article.doi}", params={})
        except httpx.HTTPError:
            return article
        item = payload.get("message", {})
        if not article.abstract:
            article.abstract = clean_cell(_strip_crossref_abstract(item.get("abstract", "")))
        if not article.keywords:
            article.keywords = clean_cell("; ".join(item.get("subject", []) or []))
        if not article.authors:
            article.authors = join_people([_author_name(author) for author in item.get("author", []) or []])
        if not article.volume:
            article.volume = clean_cell(item.get("volume", ""))
        if not article.issue:
            article.issue = clean_cell(item.get("issue", ""))
        article.publish_info = publish_info(article.volume, article.issue, article.publish_date)
        return article

    @http_retry
    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _search_page(
    client: httpx.Client,
    email: str,
    keyword: str,
    journal: str,
    issns: list[str],
    start: date,
    end: date,
    rows: int,
) -> list[dict[str, Any]]:
    filters = [
        "type:journal-article",
        f"from-pub-date:{start.isoformat()}",
        f"until-pub-date:{end.isoformat()}",
    ]
    # Collapse all ISSNs into a single OR filter
    for issn in issns:
        if issn:
            filters.append(f"issn:{issn}")
    params: dict[str, Any] = {
        "filter": ",".join(filters),
        "rows": rows,
        "sort": "published",
        "order": "desc",
    }
    if keyword:
        params["query.bibliographic"] = keyword
    if journal:
        params["query.container-title"] = journal
    if email:
        params["mailto"] = email
    try:
        response = client.get(CROSSREF_WORKS_URL, params=params)
        response.raise_for_status()
        return response.json().get("message", {}).get("items", [])
    except Exception:
        return []


def collect_crossref(config: AppConfig, start: date, end: date, max_results: int = 500) -> list[Article]:
    client = CrossrefClient(email=config.search.email)
    try:
        return client.search(config, start, end, max_results=max_results)
    finally:
        client.close()


def _user_agent(email: str) -> str:
    if email:
        return f"eclab-news/0.1 (mailto:{email})"
    return "eclab-news/0.1"


def _first(value: list[Any]) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return ""


def _published_date(item: dict[str, Any]) -> str:
    for key in ["published-print", "published-online", "published", "created"]:
        date_parts = item.get(key, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            parts = [int(part) for part in date_parts[0]]
            if len(parts) == 1:
                return f"{parts[0]:04d}"
            if len(parts) == 2:
                return f"{parts[0]:04d}-{parts[1]:02d}"
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
    return ""


def _author_name(author: dict[str, Any]) -> str:
    given = clean_cell(author.get("given", ""))
    family = clean_cell(author.get("family", ""))
    return " ".join(part for part in [given, family] if part)


def _strip_crossref_abstract(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value))
    return unescape(" ".join(text.split()))
