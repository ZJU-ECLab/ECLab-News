from __future__ import annotations

import csv
from pathlib import Path

from .models import CSV_COLUMNS, Article


def read_articles(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [ensure_row(row) for row in csv.DictReader(handle)]


def write_articles(rows: list[dict[str, str]], path: str | Path) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(ensure_row(row) for row in rows)


def write_article_rows(articles: list[Article], path: str | Path) -> None:
    rows = [article.to_row() for article in deduplicate_articles(articles)]
    write_articles(rows, path)


def ensure_row(row: dict[str, object]) -> dict[str, str]:
    return {column: str(row.get(column, "") or "") for column in CSV_COLUMNS}


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    # Sort by DOI (or title) to ensure consistent merge order regardless of
    # collection order (ThreadPoolExecutor + as_completed is non-deterministic).
    articles = sorted(articles, key=lambda a: (a.doi or a.title).casefold())
    seen: dict[str, Article] = {}
    unique: list[Article] = []
    for article in articles:
        key = article.doi.lower().strip() or article.title.lower().strip()
        if not key:
            continue
        if key in seen:
            _merge_article(seen[key], article)
            continue
        seen[key] = article
        unique.append(article)
    return unique


def _merge_article(target: Article, incoming: Article) -> None:
    for field in CSV_COLUMNS:
        current = getattr(target, field)
        new = getattr(incoming, field)
        if not str(current).strip() and str(new).strip():
            setattr(target, field, new)
    if incoming.source and incoming.source not in target.source.split("+"):
        target.source = "+".join(part for part in [target.source, incoming.source] if part)
    if incoming.source_id and incoming.source_id not in target.source_id.split("+"):
        target.source_id = "+".join(part for part in [target.source_id, incoming.source_id] if part)
