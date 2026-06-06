from __future__ import annotations

import re

from .journals import normalize_journal
from .models import Article


# Journals so on-topic that every article passes relevance without checking
CORE_EMOTION_JOURNALS = {
    "emotion",
    "emotion review",
    "cognition and emotion",
    "journal of nonverbal behavior",
    "affective neuroscience",
}

# General psychology journals: require psych relevance, but sociology/non-psych allowed through
PSYCHOLOGY_JOURNALS = {
    "journal of personality and social psychology",
    "journal of experimental social psychology",
    "social cognitive and affective neuroscience",
    "personality and social psychology bulletin",
    "personality and social psychology review",
    "psychological science",
    "current directions in psychological science",
    "perspectives on psychological science",
    "psychological bulletin",
    "psychological review",
    "psychological methods",
    "psychological inquiry",
    "american psychologist",
    "british journal of social psychology",
    "european review of social psychology",
    "social psychology and personality science",
    "advances in methods and practices in psychological science",
    "motivation and emotion",
    "current opinion in psychology",
    "psychology of aesthetics creativity and the arts",
    "cultural diversity and ethnic minority psychology",
    "journal of cross-cultural psychology",
    "journal of social and personal relationships",
    "computers in human behavior",
}

# High-prestige broad-science journals: require strong psychology AND emotion relevance
BROAD_JOURNALS = {
    "nature",
    "science",
    "nature communications",
    "nature human behaviour",
    "nature human behavior",
    "science advances",
    "proceedings of the national academy of sciences of the united states of america",
}

PSYCHOLOGY_PATTERNS = [
    r"\bpsycholog\w*\b",
    r"\bemotion\w*\b",
    r"\baffect\w*\b",
    r"\bmood\b",
    r"\bcognit\w*\b",
    r"\bsocial cognition\b",
    r"\bpersonality\b",
    r"\binterpersonal\b",
    r"\bempathy\b",
    r"\bfacial expression\w*\b",
    r"\bemotion recognition\b",
    r"\bvocal expression\w*\b",
    r"\bcross[- ]cultural\b",
    r"\bwell[- ]?being\b",
    r"\bmental health\b",
    r"\bhuman behavio\w*\b",
]

EMOTION_CORE_PATTERNS = [
    r"\bemotion\w*\b",
    r"\baffect\w*\b",
    r"\bfacial expression\w*\b",
    r"\bvocal expression\w*\b",
    r"\bemotion recognition\b",
    r"\bemotion perception\b",
    r"\bcross[- ]cultural\b",
    r"\bemotion experience\b",
    r"\bawe\b",
    r"\bshame\b",
    r"\bguilt\b",
    r"\bpride\b",
    r"\bembarrassment\b",
    r"\bfear\b.*\bemotion\b",
]

# Articles about these topics without emotion/psychology context should be excluded
SOCIOLOGY_NONPSYCH_PATTERNS = [
    r"\bimmigr\w+\b",
    r"\bvoting\b",
    r"\belectoral\b",
    r"\bpolicy\b",
    r"\bwelfare state\b",
    r"\bpolitical part\w+\b",
    r"\binequality\b",
    r"\bsocioeconomic\b",
    r"\bsociolog\w+\b",
]

HARD_SCIENCE_PATTERNS = [
    r"\bpolymer\w*\b", r"\bcataly\w*\b", r"\bchemical\w*\b", r"\bmolecule\w*\b",
    r"\bprotein\w*\b", r"\benzyme\w*\b", r"\bgenomic\w*\b", r"\bbacteri\w*\b",
    r"\btumou?r\w*\b", r"\bimmun\w*\b", r"\bgroundwater\b", r"\bquantum\b",
    r"\bsuperconduct\w*\b", r"\bnanoparticle\w*\b", r"\bcell culture\w*\b",
]


def is_psychology_relevant(article: Article) -> bool:
    journal = normalize_journal(article.journal)
    text = _article_text(article)
    if not text:
        return False

    # Core emotion journals: always pass
    if journal in CORE_EMOTION_JOURNALS:
        return True

    # Hard science: reject immediately regardless of journal
    if _count_matches(HARD_SCIENCE_PATTERNS, text) >= 1 and _count_matches(PSYCHOLOGY_PATTERNS, text) <= 1:
        return False

    # Broad journals (Nature, Science, etc.): require both psychology AND emotion signal in title
    # These journals publish widely so we filter aggressively before enrichment
    if journal in BROAD_JOURNALS:
        return _count_matches(PSYCHOLOGY_PATTERNS, text) >= 2 and _count_matches(EMOTION_CORE_PATTERNS, text) >= 1

    # Psychology journals: only reject obvious sociology/non-psych without any psych signal at all.
    # Don't require psych_score > 0 here — many relevant articles have neutral titles
    # and we haven't enriched the abstract yet at pre-filter time.
    if _count_matches(SOCIOLOGY_NONPSYCH_PATTERNS, text) >= 2 and _count_matches(PSYCHOLOGY_PATTERNS, text) == 0:
        return False

    return True


def _article_text(article: Article) -> str:
    return " ".join(
        part for part in [article.title, article.abstract, article.keywords, article.matched_keywords]
        if part
    ).casefold()


def _count_matches(patterns: list[str], text: str) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text))
