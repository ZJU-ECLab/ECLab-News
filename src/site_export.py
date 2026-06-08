from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .articles import (
    filter_renderable_rows,
    publication_info,
    title,
    unique_articles,
    url,
    value,
)
from .config import AppConfig
from .csv_io import read_articles

# Fields emitted per article. The SPA derives keyword/journal groupings itself,
# so the JSON stays a normalized flat list plus a recommended-key set.
_ARTICLE_FIELDS = (
    "title",
    "authors",
    "journal",
    "publish_info",
    "doi",
    "url",
    "abstract",
    "keywords",
    "matched_keywords",
    "category",
    "summary",
    "recommended",
)


def _label_from_dates(start: str | None, end: str | None, year: int | None, month: int | None) -> str:
    if start and end:
        return f"{start}_{end}"
    if year and month:
        return f"{year}_{month:02d}"
    return "unknown"


def _display_title(name: str, start: str | None, end: str | None, year: int | None, month: int | None) -> str:
    if start and end:
        y1, m1, d1 = start.split("-")
        y2, m2, d2 = end.split("-")
        if y1 == y2:
            return f"{name} {y1}.{m1}.{d1}-{m2}.{d2}"
        return f"{name} {y1}.{m1}.{d1}-{y2}.{m2}.{d2}"
    if year and month:
        return f"{name} {year}.{month:02d}"
    return name


def _article_payload(article: dict[str, str]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for fieldname in _ARTICLE_FIELDS:
        if fieldname == "title":
            payload["title"] = title(article)
        elif fieldname == "url":
            payload["url"] = url(article)
        elif fieldname == "publish_info":
            payload["publish_info"] = publication_info(article)
        elif fieldname == "recommended":
            payload["recommended"] = article.get("recommended", "").lower() == "true"
        else:
            payload[fieldname] = value(article, fieldname, "")
    return payload


def export_issue_json(
    config: AppConfig,
    csv_path: str,
    output_path: str,
    include_irrelevant: bool = False,
) -> dict[str, object]:
    """Write one weekly issue as a normalized JSON file for the SPA site."""
    rows = filter_renderable_rows(read_articles(csv_path), include_irrelevant)
    articles = unique_articles(rows)

    start = config.project.start_date
    end = config.project.end_date
    year = config.project.year
    month = config.project.month
    label = _label_from_dates(start, end, year, month)

    payload = {
        "label": label,
        "title": _display_title(config.project.name, start, end, year, month),
        "project": config.project.name,
        "start": start,
        "end": end,
        "year": year,
        "month": month,
        "accent_color": config.pandoc.accent_color,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": [_article_payload(a) for a in articles],
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def build_manifest(issues_dir: str | Path, output_path: str | Path) -> dict[str, object]:
    """Scan a directory of issue JSON files and write a manifest grouped for the site.

    The manifest lists every issue newest-first with lightweight metadata only
    (no article bodies), so the landing page can group by year and feature the
    latest issue without downloading every issue file.
    """
    issues_dir = Path(issues_dir)
    entries: list[dict[str, object]] = []
    for path in sorted(issues_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "label" not in data:
            continue
        rec_count = sum(1 for a in data.get("articles", []) if a.get("recommended"))
        entries.append(
            {
                "label": data.get("label"),
                "title": data.get("title"),
                "start": data.get("start"),
                "end": data.get("end"),
                "year": data.get("year"),
                "month": data.get("month"),
                "accent_color": data.get("accent_color"),
                "generated_at": data.get("generated_at"),
                "count": data.get("count", len(data.get("articles", []))),
                "recommended_count": rec_count,
                "file": f"issues/{path.name}",
            }
        )

    entries.sort(key=_sort_key, reverse=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "issues": entries,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _sort_key(entry: dict[str, object]) -> tuple:
    """Sort by start date (then end date) when present, else fall back to label."""
    start = entry.get("start")
    end = entry.get("end")
    if isinstance(start, str) and re.match(r"\d{4}-\d{2}-\d{2}", start):
        return (1, start, end if isinstance(end, str) else "")
    label = str(entry.get("label") or "")
    return (0, label, "")
