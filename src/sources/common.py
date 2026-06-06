from __future__ import annotations

from datetime import date

import httpx
from dateutil.parser import parse as parse_date
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..category import term_matches


def _retry_after_wait(exc: BaseException) -> float:
    """Return seconds to wait from Retry-After header if present."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except (ValueError, TypeError):
                pass
    return 0


def should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class _smart_wait:
    """Use Retry-After header value when available, otherwise exponential backoff."""

    def __init__(self, multiplier: float = 1, min_wait: float = 2, max_wait: float = 60):
        self._exp = wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait)

    def __call__(self, retry_state):
        exc = retry_state.outcome.exception()
        if exc:
            header_wait = _retry_after_wait(exc)
            if header_wait > 0:
                return header_wait
        return self._exp(retry_state)


def http_retry(func):
    return retry(
        retry=retry_if_exception(should_retry),
        wait=_smart_wait(multiplier=1, min_wait=2, max_wait=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )(func)


def date_in_range(value: str, start: date, end: date) -> bool:
    if not value:
        return True
    try:
        parsed = parse_date(value).date()
    except (TypeError, ValueError, OverflowError):
        return True
    return start <= parsed <= end


def doi_to_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def matched_terms(title: str, abstract: str, keywords: str, search_terms: list[str]) -> str:
    haystack = " ".join([title, abstract, keywords]).lower()
    return ", ".join(term for term in search_terms if term_matches(term, haystack))


def publish_info(volume: str, issue: str, publish_date: str) -> str:
    pieces = []
    if volume:
        pieces.append(f"Vol. {volume}")
    if issue:
        pieces.append(f"Issue {issue}")
    if publish_date:
        pieces.append(publish_date)
    return ", ".join(pieces)


def join_people(names: list[str]) -> str:
    return ", ".join(name for name in names if name)
