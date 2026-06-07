from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import httpx

from ..category import infer_categories
from ..config import AppConfig
from ..journals import article_matches_configured_journal, issns_for_journal
from ..models import Article, clean_abstract, clean_cell
from .common import date_in_range, doi_to_url, join_people, matched_terms, publish_info, http_retry

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"




class PubMedClient:
    def __init__(self, email: str = "", tool: str = "eclab-news") -> None:
        self.email = email
        self.tool = tool
        self.api_key = os.getenv("NCBI_API_KEY", "")
        self.client = httpx.Client(timeout=45, headers={"User-Agent": "eclab-news/0.1"})

    def close(self) -> None:
        self.client.close()

    def search(self, config: AppConfig, start: date, end: date, max_results: int = 500) -> list[Article]:
        term = build_pubmed_query(
            config.search.journals,
            config.search.journal_issns,
            start,
            end,
        )
        ids = self._search_ids(term, max_results=max_results)
        if not ids:
            return []
        root = self._fetch_xml(ids)
        articles = [self._pubmed_article_to_article(node, config, start, end) for node in root.findall(".//PubmedArticle")]
        collected = [article for article in articles if article is not None]
        print(f"\rCollecting PubMed: {len(collected)} target articles", flush=True)
        return collected

    def fetch_by_doi(self, doi: str, config: AppConfig) -> Article | None:
        ids = self._search_ids(f'"{doi}"[AID]', max_results=1)
        if not ids:
            return None
        root = self._fetch_xml(ids)
        node = root.find(".//PubmedArticle")
        if node is None:
            return None
        return self._pubmed_article_to_article_without_date_filter(node, config)

    def fetch_by_title(self, title: str, config: AppConfig) -> Article | None:
        ids = self._search_ids(f'"{title}"[Title]', max_results=1)
        if not ids:
            return None
        root = self._fetch_xml(ids)
        node = root.find(".//PubmedArticle")
        if node is None:
            return None
        return self._pubmed_article_to_article_without_date_filter(node, config)

    def _search_ids(self, term: str, max_results: int) -> list[str]:
        params = self._base_params(
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": str(max_results),
                "sort": "pub date",
            }
        )
        payload = self._post_json(ESEARCH_URL, data=params)
        return payload.get("esearchresult", {}).get("idlist", [])

    def _fetch_xml(self, ids: list[str]) -> ET.Element:
        params = self._base_params(
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            }
        )
        response = self._post(EFETCH_URL, data=params)
        return ET.fromstring(response.text)

    def _pubmed_article_to_article(
        self,
        node: ET.Element,
        config: AppConfig,
        start: date,
        end: date,
    ) -> Article | None:
        medline = node.find("MedlineCitation")
        article_node = medline.find("Article") if medline is not None else None
        if article_node is None:
            return None

        title = clean_cell(_text(article_node.find("ArticleTitle")))
        journal_node = article_node.find("Journal")
        journal = clean_cell(_text(journal_node.find("Title")) if journal_node is not None else "")
        issns = _journal_issns(journal_node)
        if not article_matches_configured_journal(
            journal,
            issns,
            config.search.journals,
            config.search.journal_issns,
        ):
            return None
        volume = clean_cell(_text(journal_node.find("JournalIssue/Volume")) if journal_node is not None else "")
        issue = clean_cell(_text(journal_node.find("JournalIssue/Issue")) if journal_node is not None else "")
        publish_date = _publication_date(article_node)
        if not date_in_range(publish_date, start, end):
            return None
        return self._article_node_to_article(node, article_node, medline, journal, volume, issue, publish_date, config)

    def _pubmed_article_to_article_without_date_filter(
        self,
        node: ET.Element,
        config: AppConfig,
    ) -> Article | None:
        medline = node.find("MedlineCitation")
        article_node = medline.find("Article") if medline is not None else None
        if article_node is None:
            return None
        journal_node = article_node.find("Journal")
        journal = clean_cell(_text(journal_node.find("Title")) if journal_node is not None else "")
        volume = clean_cell(_text(journal_node.find("JournalIssue/Volume")) if journal_node is not None else "")
        issue = clean_cell(_text(journal_node.find("JournalIssue/Issue")) if journal_node is not None else "")
        publish_date = _publication_date(article_node)
        return self._article_node_to_article(node, article_node, medline, journal, volume, issue, publish_date, config)

    def _article_node_to_article(
        self,
        node: ET.Element,
        article_node: ET.Element,
        medline: ET.Element | None,
        journal: str,
        volume: str,
        issue: str,
        publish_date: str,
        config: AppConfig,
    ) -> Article | None:
        title = clean_cell(_text(article_node.find("ArticleTitle")))

        abstract = clean_abstract(" ".join(_text(item) for item in article_node.findall("Abstract/AbstractText")))
        if config.search.require_abstract and not abstract:
            return None
        keywords = clean_cell("; ".join(_text(item) for item in medline.findall("KeywordList/Keyword")) if medline is not None else "")
        doi = clean_cell(_doi(node))
        pmid = clean_cell(_text(medline.find("PMID")) if medline is not None else "")
        matched = matched_terms(title, abstract, keywords, config.search.keywords)
        category = infer_categories(title, abstract, keywords, matched, config.categories)

        return Article(
            title=title,
            authors=join_people(_authors(article_node)),
            journal=journal,
            volume=volume,
            issue=issue,
            publish_date=publish_date,
            publish_info=publish_info(volume, issue, publish_date),
            doi=doi,
            url=doi_to_url(doi) or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""),
            abstract=abstract,
            keywords=keywords,
            matched_keywords=matched,
            category=category or matched,
            source="pubmed",
            source_id=pmid,
        )

    def _base_params(self, params: dict[str, str]) -> dict[str, str]:
        base = {"tool": self.tool}
        if self.email:
            base["email"] = self.email
        if self.api_key:
            base["api_key"] = self.api_key
        base.update(params)
        return base

    @http_retry
    def _post_json(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(url, data=data)
        response.raise_for_status()
        return response.json()

    @http_retry
    def _post(self, url: str, data: dict[str, Any]) -> httpx.Response:
        response = self.client.post(url, data=data)
        response.raise_for_status()
        return response


def collect_pubmed(config: AppConfig, start: date, end: date, max_results: int = 500) -> list[Article]:
    client = PubMedClient(email=config.search.email, tool=config.search.ncbi_tool)
    try:
        return client.search(config, start, end, max_results=max_results)
    finally:
        client.close()


def build_pubmed_query(
    journals: list[str],
    journal_issns: dict[str, list[str]],
    start: date,
    end: date,
) -> str:
    parts = []
    if journals:
        journal_terms = []
        for journal in journals:
            journal_terms.append(f'"{journal}"[Journal]')
            journal_terms.extend(f'"{issn}"[ISSN]' for issn in issns_for_journal(journal, journal_issns))
        parts.append(f"({' OR '.join(journal_terms)})")
    parts.append(f'("{start.isoformat()}"[Date - Publication] : "{end.isoformat()}"[Date - Publication])')
    return " AND ".join(parts)


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _publication_date(article_node: ET.Element) -> str:
    for path in ["Journal/JournalIssue/PubDate", "ArticleDate"]:
        date_node = article_node.find(path)
        if date_node is not None:
            year = _text(date_node.find("Year"))
            month = _month_to_number(_text(date_node.find("Month")))
            day = _text(date_node.find("Day"))
            if year and month and day:
                return f"{year}-{month}-{int(day):02d}"
            if year and month:
                return f"{year}-{month}"
            if year:
                return year
            medline_date = _text(date_node.find("MedlineDate"))
            if medline_date:
                return medline_date
    return ""


def _month_to_number(value: str) -> str:
    if not value:
        return ""
    if value.isdigit():
        return f"{int(value):02d}"
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    return months.get(value[:3].lower(), "")


def _doi(node: ET.Element) -> str:
    for article_id in node.findall(".//ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            return _text(article_id)
    for elocation in node.findall(".//ELocationID"):
        if elocation.attrib.get("EIdType") == "doi":
            return _text(elocation)
    return ""


def _journal_issns(journal_node: ET.Element | None) -> list[str]:
    if journal_node is None:
        return []
    return [_text(issn) for issn in journal_node.findall("ISSN") if _text(issn)]


def _authors(article_node: ET.Element) -> list[str]:
    names = []
    for author in article_node.findall("AuthorList/Author"):
        collective = _text(author.find("CollectiveName"))
        if collective:
            names.append(collective)
            continue
        fore_name = _text(author.find("ForeName"))
        last_name = _text(author.find("LastName"))
        names.append(" ".join(part for part in [fore_name, last_name] if part))
    return names
