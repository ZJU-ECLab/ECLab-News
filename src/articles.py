from __future__ import annotations

import re
from collections import OrderedDict

from .category import upper_or_capitalize


def filter_renderable_rows(
    rows: list[dict[str, str]],
    include_irrelevant: bool = False,
) -> list[dict[str, str]]:
    if include_irrelevant:
        return rows
    return [
        row
        for row in rows
        if str(row.get("summary", "")).strip() != "0"
        and str(row.get("relevant", "")).lower() != "false"
    ]


def categorize_articles(rows: list[dict[str, str]]) -> OrderedDict[str, list[dict[str, str]]]:
    categories: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        title = value(row, "title", "")
        if not title:
            continue
        category_text = value(row, "category", "") or value(row, "matched_keywords", "")
        row_categories = [upper_or_capitalize(item.strip()) for item in category_text.split(",") if item.strip()]
        if not row_categories:
            row_categories = ["Uncategorized"]
        for category in row_categories:
            key = (category, article_key(row))
            if key in seen:
                continue
            seen.add(key)
            categories.setdefault(category, []).append(row)
    sorted_keys = sorted(
        (k for k in categories if k != "Uncategorized"),
        key=str.casefold,
    )
    if "Uncategorized" in categories:
        sorted_keys.append("Uncategorized")
    return OrderedDict((k, categories[k]) for k in sorted_keys)


def categorize_by_journal(rows: list[dict[str, str]]) -> OrderedDict[str, list[dict[str, str]]]:
    """Group articles by their journal name."""
    journals: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    seen: set[str] = set()
    for row in rows:
        title = value(row, "title", "")
        if not title:
            continue
        journal_name = value(row, "journal", "Unknown Journal")
        key = article_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        journals.setdefault(journal_name, []).append(row)
    return OrderedDict(sorted(journals.items(), key=lambda x: x[0].casefold()))


def recommended_articles(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return articles marked as recommended."""
    seen: set[str] = set()
    recommended: list[dict[str, str]] = []
    for row in rows:
        if row.get("recommended", "").lower() != "true":
            continue
        key = article_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        recommended.append(row)
    return recommended


def unique_articles(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in rows:
        key = article_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def article_key(article: dict[str, str]) -> str:
    return value(article, "doi", "").lower() or value(article, "title", "").lower()


def article_anchor(article: dict[str, str], index: int) -> str:
    title = value(article, "title", f"article-{index}")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"article-{index}-{slug[:48]}" if slug else f"article-{index}"


def value(article: dict[str, str], key: str, placeholder: str) -> str:
    current = str(article.get(key, "") or "").strip()
    if current and current != "0":
        return current
    return placeholder


def title(article: dict[str, str]) -> str:
    return value(article, "title", "标题信息缺失")


def url(article: dict[str, str]) -> str:
    direct_url = value(article, "url", "")
    doi = value(article, "doi", "")
    return direct_url or (f"https://doi.org/{doi}" if doi else "")


def publication_info(article: dict[str, str]) -> str:
    pieces = [
        value(article, "journal", "期刊信息缺失"),
        value(article, "publish_info", ""),
    ]
    return ", ".join(piece for piece in pieces if piece)

