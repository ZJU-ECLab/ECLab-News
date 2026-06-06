from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectConfig:
    name: str = "东西情报"
    year: int | None = None
    month: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    editor_in_chief: list[str] = field(default_factory=list)
    wechat_full_version_url: str = ""


@dataclass
class PandocConfig:
    accent_color: str = "#8b3a3a"


@dataclass
class SearchConfig:
    sources: list[str] = field(default_factory=lambda: ["crossref", "pubmed"])
    keywords: list[str] = field(default_factory=list)
    journals: list[str] = field(default_factory=list)
    journal_issns: dict[str, list[str]] = field(default_factory=dict)
    journal_sources: dict[str, list[str]] = field(default_factory=dict)  # journal -> ["pubmed"|"crossref"]
    email: str = ""
    ncbi_tool: str = "eclab-news"
    require_abstract: bool = False
    exclude_supplemental: bool = True


@dataclass
class LLMConfig:
    provider: str = "litellm"
    model: str = "openai/mimo"
    temperature: float = 0.2
    api_key_env: str = "LLM_API_KEY"
    api_base_env: str = "LLM_API_BASE"
    system_prompt: str = ""
    user_prompt: str = ""


@dataclass
class AppConfig:
    project: ProjectConfig
    search: SearchConfig
    llm: LLMConfig
    pandoc: PandocConfig
    categories: dict[str, list[str]]


def load_config(path: str | Path) -> AppConfig:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    project_raw = raw.get("project", {})
    search_raw = raw.get("search", {})
    llm_raw = raw.get("llm", {})
    prompt_raw = llm_raw.get("prompt", {})
    pandoc_raw = raw.get("pandoc", {})

    return AppConfig(
        project=ProjectConfig(
            name=project_raw.get("name", "东西情报"),
            year=project_raw.get("year"),
            month=project_raw.get("month"),
            editor_in_chief=list(project_raw.get("editor_in_chief", [])),
            wechat_full_version_url=project_raw.get("wechat_full_version_url", ""),
        ),
        search=SearchConfig(
            sources=_normalize_sources(search_raw),
            keywords=list(search_raw.get("keywords", [])),
            journals=list(search_raw.get("journals", [])),
            journal_issns=_normalize_journal_issns(search_raw.get("journal_issns", {})),
            journal_sources=_normalize_journal_sources(search_raw.get("journal_sources", {})),
            email=search_raw.get("email", ""),
            ncbi_tool=search_raw.get("ncbi_tool", "eclab-news"),
            require_abstract=bool(search_raw.get("require_abstract", False)),
            exclude_supplemental=bool(search_raw.get("exclude_supplemental", True)),
        ),
        llm=LLMConfig(
            provider=llm_raw.get("provider", "litellm"),
            model=llm_raw.get("model", "openai/mimo"),
            temperature=float(llm_raw.get("temperature", 0.2)),
            api_key_env=llm_raw.get("api_key_env", "LLM_API_KEY"),
            api_base_env=llm_raw.get("api_base_env", "LLM_API_BASE"),
            system_prompt=prompt_raw.get("system", ""),
            user_prompt=prompt_raw.get("user", ""),
        ),
        pandoc=PandocConfig(
            accent_color=pandoc_raw.get("accent_color", "#8b3a3a"),
        ),
        categories=_normalize_categories(raw.get("categories", {})),
    )


def _normalize_categories(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    categories: dict[str, list[str]] = {}
    for name, terms in value.items():
        if isinstance(terms, str):
            categories[str(name)] = [terms]
        elif isinstance(terms, list):
            categories[str(name)] = [str(term) for term in terms]
    return categories


def _normalize_sources(search_raw: dict[str, Any]) -> list[str]:
    if "sources" in search_raw:
        sources = search_raw.get("sources", [])
        if isinstance(sources, str):
            return [sources]
        return [str(source) for source in sources]
    source = search_raw.get("source")
    if source:
        return [str(source)]
    return ["crossref", "pubmed"]


def _normalize_journal_issns(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, list[str]] = {}
    for journal, issns in value.items():
        if isinstance(issns, str):
            output[str(journal)] = [issns]
        elif isinstance(issns, list):
            output[str(journal)] = [str(issn) for issn in issns]
    return output


def _normalize_journal_sources(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, list[str]] = {}
    for journal, sources in value.items():
        if isinstance(sources, str):
            output[str(journal)] = [sources]
        elif isinstance(sources, list):
            output[str(journal)] = [str(s) for s in sources]
    return output
