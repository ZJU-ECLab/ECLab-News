"""Last-resort abstract recovery by scraping publisher/DOI landing pages.

This module is the final fallback after the normal metadata-API enrichment
chain (Crossref → OpenAlex → Semantic Scholar → PubMed → Scopus). Some
journals (notably APA's *Psychology of Aesthetics, Creativity, and the Arts*
and Taylor & Francis' *European Review of Social Psychology*) routinely omit
abstracts from those APIs, so we fetch the HTML landing pages and extract the
abstract directly.

All network/parsing failures are non-fatal: callers get ``None`` and the
collection pipeline continues unchanged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from ..models import Article, clean_abstract

_USER_AGENT = "eclab-news/0.1 (Emotion and Culture Lab literature digest; mailto:)"
_MIN_ABSTRACT_CHARS = 250

# UI / boilerplate phrases that indicate we scraped a paywall or cookie wall
# rather than a real abstract.
_UI_NOISE_PHRASES = (
    "sign in",
    "log in",
    "cookie",
    "download citation",
    "request full-text",
    "request full text",
    "discover the world's research",
    "we use cookies",
    "your browser",
    "javascript is disabled",
    "access through your institution",
    "purchase this article",
    "add to cart",
)


@dataclass
class AbstractRecoveryResult:
    abstract: str
    source_url: str
    method: str
    confidence: float


# ---------------------------------------------------------------------------
# Title slug / candidate URL generation
# ---------------------------------------------------------------------------


def slugify_title(title: str) -> str:
    """Slug from the main title (text before the first colon).

    Lowercased, punctuation removed, spaces collapsed to single hyphens.
    """
    main = title.split(":", 1)[0]
    main = main.casefold()
    main = re.sub(r"[^a-z0-9\s-]+", "", main)
    main = re.sub(r"[\s-]+", "-", main).strip("-")
    return main


def candidate_urls(doi: str, title: str) -> list[str]:
    """Ordered list of landing-page URLs to try for a given DOI/title."""
    urls: list[str] = []
    doi = (doi or "").strip()
    if doi:
        urls.append(f"https://doi.org/{doi}")
        prefix = doi.split("/", 1)[0]
        if prefix == "10.1080":  # Taylor & Francis
            urls.append(f"https://www.tandfonline.com/doi/full/{doi}")
            urls.append(f"https://www.tandfonline.com/doi/abs/{doi}")
        elif prefix == "10.1037":  # APA
            slug = slugify_title(title)
            if slug:
                urls.append(f"https://www.ovid.com/journals/paca/abstract/{doi}~{slug}")
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# ---------------------------------------------------------------------------
# Abstract validation
# ---------------------------------------------------------------------------


def looks_like_abstract(text: str) -> bool:
    """Heuristic: does ``text`` look like a real abstract (vs UI/boilerplate)?"""
    if not text:
        return False
    normalized = " ".join(text.split())
    if len(normalized) < _MIN_ABSTRACT_CHARS:
        return False
    lowered = normalized.casefold()
    # Reject if dominated by UI/boilerplate noise.
    if any(phrase in lowered for phrase in _UI_NOISE_PHRASES):
        return False
    # Prefer paragraph-like prose: at least two sentence terminators.
    sentence_terminators = normalized.count(". ") + normalized.count("。")
    if sentence_terminators < 1:
        return False
    return True


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------


class _MetaCollector(HTMLParser):
    """Collect <meta> tags, <script type=application/ld+json> blocks, and a
    coarse text representation (with markers for abstract-ish containers)."""

    _ABSTRACT_TAGS = {"div", "section", "p", "span"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: list[dict[str, str]] = []
        self.ldjson_blocks: list[str] = []
        self.abstract_chunks: list[str] = []
        self._in_ldjson = False
        self._abstract_depth = 0
        self._depth = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            self.metas.append(attr)
            return
        if tag == "script" and attr.get("type", "").lower() == "application/ld+json":
            self._in_ldjson = True
            return
        if tag in self._ABSTRACT_TAGS:
            self._depth += 1
            ident = " ".join([attr.get("class", ""), attr.get("id", ""), attr.get("property", "")]).lower()
            if "abstract" in ident:
                # Begin capturing this container's text.
                self._abstract_depth = self._depth

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ldjson:
            self._in_ldjson = False
            return
        if tag in self._ABSTRACT_TAGS:
            if self._abstract_depth and self._depth <= self._abstract_depth:
                self.abstract_chunks.append(" ".join(self._text_parts))
                self._text_parts = []
                self._abstract_depth = 0
            if self._depth > 0:
                self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_ldjson:
            self.ldjson_blocks.append(data)
        elif self._abstract_depth:
            text = data.strip()
            if text:
                self._text_parts.append(text)


def _meta_content(metas: list[dict[str, str]], key: str, value: str) -> str:
    """Return the ``content`` of the first <meta> whose key attr == value."""
    value_l = value.casefold()
    for meta in metas:
        if meta.get(key, "").casefold() == value_l:
            content = meta.get("content", "").strip()
            if content:
                return content
    return ""


def _extract_from_ldjson(blocks: list[str]) -> str:
    for block in blocks:
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for candidate in _walk_ldjson(data):
            for field in ("abstract", "description"):
                value = candidate.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _walk_ldjson(data: object) -> list[dict]:
    found: list[dict] = []
    if isinstance(data, dict):
        found.append(data)
        for value in data.values():
            found.extend(_walk_ldjson(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_walk_ldjson(item))
    return found


_TAG_RE = re.compile(r"<[^>]+>")
_ABSTRACT_HEADING_RE = re.compile(
    r"(?is)<(?:h[1-6]|strong|b)[^>]*>\s*(?:abstract(?:\s+and\s+figures)?|summary)\s*</(?:h[1-6]|strong|b)>(.*?)"
    r"(?:<(?:h[1-6])[^>]*>\s*(?:keywords?|references?|figures?|citations?|full[\s-]?text|author content)\b|\Z)"
)


def _strip_html(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    return unescape(" ".join(text.split()))


def _extract_from_heading(html: str) -> str:
    match = _ABSTRACT_HEADING_RE.search(html)
    if match:
        return _strip_html(match.group(1))
    return ""


def extract_abstract_from_html(html: str) -> tuple[str, str]:
    """Extract an abstract from raw HTML.

    Returns ``(abstract, method)`` where ``method`` names the strategy used,
    or ``("", "")`` if nothing usable was found. Validation via
    :func:`looks_like_abstract` is the caller's responsibility, but each
    strategy returns the first candidate that already passes validation.
    """
    if not html:
        return "", ""

    parser = _MetaCollector()
    try:
        parser.feed(html)
    except Exception:
        pass

    # a. Metadata extraction
    meta_strategies = [
        ("name", "citation_abstract", "meta_citation_abstract"),
        ("name", "dc.description", "meta_dc_description"),
        ("name", "description", "meta_description"),
        ("property", "og:description", "meta_og_description"),
        ("name", "twitter:description", "meta_twitter_description"),
    ]
    for key, value, method in meta_strategies:
        content = clean_abstract(_meta_content(parser.metas, key, value))
        if looks_like_abstract(content):
            return content, method

    # b. JSON-LD extraction
    ld = clean_abstract(_extract_from_ldjson(parser.ldjson_blocks))
    if looks_like_abstract(ld):
        return ld, "json_ld"

    # c. Publisher / generic abstract containers (captured during parse)
    for chunk in parser.abstract_chunks:
        candidate = clean_abstract(chunk)
        if looks_like_abstract(candidate):
            return candidate, "html_container"

    # d. Text fallback: locate an "Abstract"/"Summary" heading
    heading = clean_abstract(_extract_from_heading(html))
    if looks_like_abstract(heading):
        return heading, "html_heading"

    return "", ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _fetch_html(client: httpx.Client, url: str) -> str:
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return ""
    if response.status_code in (403, 404, 429) or response.status_code >= 500:
        return ""
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "xml" not in content_type and content_type:
        return ""
    return response.text


def recover_missing_abstract(
    article: Article,
    *,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> AbstractRecoveryResult | None:
    """Attempt to recover a missing abstract by scraping landing pages.

    Returns an :class:`AbstractRecoveryResult` on success, otherwise ``None``.
    Never raises for network/parsing problems.
    """
    doi = (article.doi or "").strip()
    title = (article.title or "").strip()
    # Need a DOI or a distinctive (reasonably long) title to find a page.
    if not doi and len(title) < 20:
        return None

    urls = candidate_urls(doi, title)
    if not urls:
        return None

    owns_client = client is None
    if owns_client:
        client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
    try:
        for url in urls:
            html = _fetch_html(client, url)
            if not html:
                continue
            abstract, method = extract_abstract_from_html(html)
            if abstract:
                confidence = 0.9 if method.startswith("meta_citation") or method == "json_ld" else 0.7
                return AbstractRecoveryResult(
                    abstract=abstract,
                    source_url=url,
                    method=method,
                    confidence=confidence,
                )
    finally:
        if owns_client:
            client.close()
    return None
