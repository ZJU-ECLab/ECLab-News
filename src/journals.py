from __future__ import annotations

from html import unescape


def is_configured_journal(journal: str, configured_journals: list[str]) -> bool:
    if not configured_journals:
        return True
    normalized = normalize_journal(journal)
    return normalized in {normalize_journal(item) for item in configured_journals}


def article_matches_configured_journal(
    journal: str,
    article_issns: list[str],
    configured_journals: list[str],
    journal_issns: dict[str, list[str]],
) -> bool:
    configured_issns = all_configured_issns(journal_issns)
    normalized_article_issns = {normalize_issn(issn) for issn in article_issns if issn}
    if configured_issns and normalized_article_issns.intersection(configured_issns):
        return True
    return is_configured_journal(journal, configured_journals)


def all_configured_issns(journal_issns: dict[str, list[str]]) -> set[str]:
    return {
        normalize_issn(issn)
        for issns in journal_issns.values()
        for issn in issns
        if issn
    }


def issns_for_journal(journal: str, journal_issns: dict[str, list[str]]) -> list[str]:
    normalized = normalize_journal(journal)
    for configured_journal, issns in journal_issns.items():
        if normalize_journal(configured_journal) == normalized:
            return issns
    return []


def canonical_journal(journal: str, configured_journals: list[str]) -> str:
    normalized = normalize_journal(journal)
    for configured in configured_journals:
        if normalized == normalize_journal(configured):
            return configured
    return journal


def normalize_journal(value: str) -> str:
    return unescape(value).casefold().replace("&", "and").replace(".", "").strip()


def normalize_issn(value: str) -> str:
    return value.casefold().replace("-", "").strip()


def looks_supplemental(title: str, doi: str) -> bool:
    normalized_title = title.casefold().strip()
    normalized_doi = doi.casefold().strip()
    non_research_prefixes = (
        "supplemental material",
        "correction to",
        "erratum",
        "matters arising",
        "reply to",
        "response to",
        "author reply",
        "retraction",
        "research briefing",
        "news & views",
        "news and views",
        "correspondence:",
        "editorial board",
        "editorial:",
        "editorial ",
    )
    non_research_exact = {"editorial"}
    return (
        any(normalized_title.startswith(p) for p in non_research_prefixes)
        or normalized_title in non_research_exact
        or normalized_doi.endswith(".supp")
        or ".supp" in normalized_doi
    )
