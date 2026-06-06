from __future__ import annotations

import re


def infer_categories(
    title: str,
    abstract: str,
    keywords: str,
    matched_keywords: str,
    category_terms: dict[str, list[str]],
) -> str:
    haystack = " ".join([title, abstract, keywords, matched_keywords]).lower()
    matches: list[str] = []
    for category, terms in category_terms.items():
        if any(term_matches(term, haystack) for term in terms):
            matches.append(category)
    return ", ".join(matches)


def upper_or_capitalize(category: str) -> str:
    return category if category.upper() == category else category.capitalize()


def term_matches(term: str, haystack: str) -> bool:
    normalized = term.lower().strip()
    if not normalized:
        return False
    if len(normalized) <= 3 and normalized.isalnum():
        return re.search(rf"\b{re.escape(normalized)}\b", haystack) is not None
    if normalized.isalnum():
        return re.search(rf"\b{re.escape(normalized)}\b", haystack) is not None
    return normalized in haystack
