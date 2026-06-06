from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .category import infer_categories
from .config import AppConfig
from .csv_io import deduplicate_articles
from .journals import canonical_journal, is_configured_journal, looks_supplemental
from .models import Article
from .relevance import is_psychology_relevant
from .sources.common import date_in_range, matched_terms, publish_info
from .sources.crossref import CrossrefClient
from .sources.openalex import OpenAlexClient
from .sources.pubmed import PubMedClient
from .sources.scopus import ScopusClient
from .sources.semanticscholar import SemanticScholarClient

_ENRICH_WORKERS = 5


def process_articles(
    config: AppConfig,
    start=None,
    end=None,
    articles: list[Article] | None = None,
) -> list[Article]:
    articles = articles or []
    n_raw = len(articles)

    articles = _filter_structural(config, articles, start, end)
    articles = deduplicate_articles(articles)
    print(f"  → {len(articles)} after structural filter + dedup (from {n_raw} collected)")

    # Pre-filter relevance on available data before expensive enrichment
    pre = [a for a in articles if is_psychology_relevant(a)]
    print(f"  → {len(pre)} passed relevance pre-filter ({len(articles) - len(pre)} dropped)")
    articles = pre

    articles = enrich_articles(config, articles)

    for article in articles:
        _refresh_derived_fields(article, config)
    articles = filter_articles(config, articles, start=start, end=end,
                               require_abstract=config.search.require_abstract,
                               require_relevance=True)
    return articles


def _filter_structural(
    config: AppConfig,
    articles: list[Article],
    start=None,
    end=None,
) -> list[Article]:
    """Fast structural filters — no API calls, just field checks."""
    kept: list[Article] = []
    for article in articles:
        if not article.title or not article.journal:
            continue
        if not is_configured_journal(article.journal, config.search.journals):
            continue
        if config.search.exclude_supplemental and looks_supplemental(article.title, article.doi):
            continue
        if start and end and not date_in_range(article.publish_date, start, end):
            continue
        kept.append(article)
    return kept


def filter_articles(
    config: AppConfig,
    articles: list[Article],
    start=None,
    end=None,
    require_abstract: bool = False,
    require_relevance: bool = True,
) -> list[Article]:
    kept: list[Article] = []
    reasons = {
        "missing_title_or_journal": 0,
        "journal": 0,
        "supplemental": 0,
        "date": 0,
        "abstract": 0,
        "relevance": 0,
    }
    for article in articles:
        keep, reason = _keep_article(
            article, config, start, end,
            require_abstract=require_abstract,
            require_relevance=require_relevance,
        )
        if keep:
            kept.append(article)
        elif reason:
            reasons[reason] += 1

    removed = len(articles) - len(kept)
    if removed:
        details = ", ".join(f"{reason}={count}" for reason, count in reasons.items() if count)
        print(f"Filtered articles: kept {len(kept)}/{len(articles)}; removed {removed} ({details})")
    else:
        print(f"Filtered articles: kept {len(kept)}/{len(articles)}")
    return kept


def _keep_article(
    article: Article,
    config: AppConfig,
    start,
    end,
    require_abstract: bool,
    require_relevance: bool,
) -> tuple[bool, str]:
    _refresh_derived_fields(article, config)
    if not article.title or not article.journal:
        return False, "missing_title_or_journal"
    if not is_configured_journal(article.journal, config.search.journals):
        return False, "journal"
    if config.search.exclude_supplemental and looks_supplemental(article.title, article.doi):
        return False, "supplemental"
    if start and end and not date_in_range(article.publish_date, start, end):
        return False, "date"
    if require_abstract and not article.abstract:
        return False, "abstract"
    if require_relevance and not is_psychology_relevant(article):
        return False, "relevance"
    return True, ""


def _needs_enrichment(article: Article) -> bool:
    """Check if an article needs any enrichment at all."""
    return not article.abstract or not article.keywords or not article.authors


def enrich_articles(config: AppConfig, articles: list[Article]) -> list[Article]:
    if not articles:
        return articles

    # Skip articles that already have all fields
    needs_work = [a for a in articles if _needs_enrichment(a)]
    n_complete = len(articles) - len(needs_work)
    n_to_enrich = len(needs_work)
    print(f"Enriching {n_to_enrich} articles ({n_complete} already complete)...")
    if not needs_work:
        return articles

    total = len(needs_work)
    use_scopus = bool(os.getenv("SCOPUS_API_KEY"))

    def _enrich_one(article: Article) -> Article:
        # Each thread creates its own clients (httpx.Client is not thread-safe)
        crossref = CrossrefClient(email=config.search.email)
        openalex = OpenAlexClient(email=config.search.email)
        s2 = SemanticScholarClient()
        pubmed = PubMedClient(email=config.search.email, tool=config.search.ncbi_tool)
        scopus = ScopusClient() if use_scopus else None
        try:
            # Order: fast single-request sources first, slow multi-request sources last
            # 1. Crossref DOI lookup (fast, often has keywords/authors)
            if article.doi:
                crossref._enrich_missing(article)
            if not _needs_enrichment(article):
                return article

            # 2. OpenAlex DOI lookup (fast, 1 request)
            if article.doi:
                oa = openalex.fetch_by_doi(article.doi)
                if oa is not None:
                    _merge_missing(article, oa)
            if not _needs_enrichment(article):
                return article

            # 3. Semantic Scholar DOI lookup (fast, 1 request)
            if article.doi:
                s2a = s2.fetch_by_doi(article.doi)
                if s2a is not None:
                    _merge_missing(article, s2a)
            if not _needs_enrichment(article):
                return article

            # 4. OpenAlex title search fallback (1 request, for paywalled journals)
            if article.title and not article.abstract:
                oa = openalex.fetch_by_title(article.title)
                if oa is not None:
                    _merge_missing(article, oa)
            if not _needs_enrichment(article):
                return article

            # 5. PubMed DOI search (slow, 2 requests — only if still missing)
            if article.doi and (not article.abstract or not article.keywords):
                pa = pubmed.fetch_by_doi(article.doi, config)
                if pa is not None:
                    _merge_missing(article, pa)
            if not _needs_enrichment(article):
                return article

            # 5b. PubMed title search fallback (for paywalled/crossref-only journals)
            if article.title and not article.abstract:
                pa = pubmed.fetch_by_title(article.title, config)
                if pa is not None:
                    _merge_missing(article, pa)
            if not _needs_enrichment(article):
                return article

            # 6. Scopus DOI lookup (last resort, requires API key)
            if scopus and article.doi and (not article.abstract or not article.keywords):
                sa = scopus.fetch_by_doi(article.doi)
                if sa is not None:
                    _merge_missing(article, sa)
        finally:
            crossref.close()
            openalex.close()
            s2.close()
            pubmed.close()
            if scopus:
                scopus.close()
        return article

    with ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as pool:
        futures = {pool.submit(_enrich_one, a): i for i, a in enumerate(needs_work)}
        results = [None] * total
        for done, future in enumerate(as_completed(futures), 1):
            idx = futures[future]
            results[idx] = future.result()
            print(f"\rEnriching articles: {done}/{total}", end="", flush=True)

    print()
    # results is indexed to needs_work; merge back preserving original order
    enriched_map = {id(needs_work[i]): results[i] for i in range(total) if results[i] is not None}
    return [enriched_map.get(id(a), a) for a in articles]


def _merge_missing(target: Article, incoming: Article) -> None:
    for field in Article.__dataclass_fields__:
        if not str(getattr(target, field)).strip() and str(getattr(incoming, field)).strip():
            setattr(target, field, getattr(incoming, field))
    if incoming.source and incoming.source not in target.source.split("+"):
        target.source = "+".join(part for part in [target.source, incoming.source] if part)
    if incoming.source_id and incoming.source_id not in target.source_id.split("+"):
        target.source_id = "+".join(part for part in [target.source_id, incoming.source_id] if part)


def _refresh_derived_fields(article: Article, config: AppConfig) -> None:
    article.journal = canonical_journal(article.journal, config.search.journals)
    article.publish_info = publish_info(article.volume, article.issue, article.publish_date)
    article.matched_keywords = matched_terms(
        article.title, article.abstract, article.keywords, config.search.keywords
    )
    article.category = infer_categories(
        article.title,
        article.abstract,
        article.keywords,
        article.matched_keywords,
        config.categories,
    ) or article.matched_keywords
