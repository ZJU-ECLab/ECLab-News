from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from .articles import (
    article_anchor,
    categorize_articles,
    categorize_by_journal,
    filter_renderable_rows,
    publication_info,
    recommended_articles,
    title,
    unique_articles,
    url,
    value,
)
from .category import upper_or_capitalize
from .config import AppConfig
from .csv_io import read_articles

REC_LABEL = "⭐ 推荐阅读"


def render_markdown(
    config: AppConfig,
    csv_path: str,
    output_path: str,
    variant: str = "lab",
    include_irrelevant: bool = False,
) -> None:
    rows = filter_renderable_rows(read_articles(csv_path), include_irrelevant)
    categories = categorize_articles(rows)
    content = (
        render_lab_markdown(config, categories, rows)
        if variant == "lab"
        else render_wechat_markdown(config, categories)
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def render_lab_markdown(
    config: AppConfig,
    categories: OrderedDict[str, list[dict[str, str]]],
    rows: list[dict[str, str]],
) -> str:
    article_list = unique_articles(rows)
    anchors = {id(article): article_anchor(article, index) for index, article in enumerate(article_list, 1)}
    journal_categories = categorize_by_journal(rows)
    recommended = recommended_articles(rows)
    rec_dois = {value(a, "doi", "").lower() for a in recommended}
    lines = _lab_header(config)
    lines.extend(["", "## 索引", ""])

    # Keyword index
    lines.extend(['<div class="index-section" data-view="keywords">', ""])
    if recommended:
        lines.extend([f'<div class="category-section" data-category="{REC_LABEL}">', ""])
        lines.extend([f"### {REC_LABEL}", ""])
        lines.extend(_render_article_list(recommended, anchors, rec_dois))
        lines.extend(["</div>", ""])
    for category, articles in categories.items():
        lines.extend([f'<div class="category-section" data-category="{category}">', ""])
        lines.extend([f"### 关键词：{category}", ""])
        lines.extend(_render_article_list(articles, anchors, rec_dois))
        lines.extend(["</div>", ""])
    lines.extend(["</div>", ""])

    # Journal index
    lines.extend(['<div class="index-section" data-view="journals" style="display:none">', ""])
    if recommended:
        lines.extend([f'<div class="category-section" data-journal="{REC_LABEL}">', ""])
        lines.extend([f"### {REC_LABEL}", ""])
        lines.extend(_render_article_list(recommended, anchors, rec_dois))
        lines.extend(["</div>", ""])
    for journal, articles in journal_categories.items():
        lines.extend([f'<div class="category-section" data-journal="{journal}">', ""])
        lines.extend([f"### 📖 {journal}", ""])
        lines.extend(_render_article_list(articles, anchors, rec_dois))
        lines.extend(["</div>", ""])
    lines.extend(["</div>", ""])

    lines.extend(["---", "", "## 文献详情", ""])
    for index, article in enumerate(article_list, 1):
        anchor = anchors[id(article)]
        is_rec = article.get("recommended", "") == "true"
        rec_line = ["", "**⭐ 推荐阅读**"] if is_rec else []
        abstract = value(article, "abstract", "摘要缺失")
        lines.extend(
            [
                f'<a id="{anchor}"></a>',
                "",
                f"### {index}. {title(article)}",
                *rec_line,
                "",
                f"**作者：** {value(article, 'authors', '作者信息缺失')}",
                "",
                f"**链接：** {_url_markdown(article)}",
                "",
                f"**发表信息：** {publication_info(article)}",
                "",
                f"**关键词：** {value(article, 'keywords', '关键词缺失')}",
                "",
                f"**摘要：** {abstract}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _render_article_list(
    articles: list[dict[str, str]],
    anchors: dict[int, str],
    rec_dois: set[str],
) -> list[str]:
    lines: list[str] = []
    for article in articles:
        anchor = anchors.get(id(article), "")
        doi = value(article, "doi", "").lower()
        is_rec = doi in rec_dois
        journal_name = value(article, "journal", "")
        category_text = value(article, "category", "") or value(article, "matched_keywords", "")
        keywords = [upper_or_capitalize(k.strip()) for k in category_text.split(",") if k.strip()]
        tags = _build_tags_html(is_rec, journal_name, keywords)
        summary = value(article, "summary", "摘要或总结缺失")
        rec_attr = ' data-recommended="true"' if is_rec else ""
        lines.append("")
        lines.append(f'<div class="article-index-item" data-anchor="{anchor}"{rec_attr}>')
        lines.append(f'<div class="article-index-title"><a href="#{anchor}">{title(article)}</a></div>')
        lines.append(f'<div class="article-index-tags">{tags}</div>')
        lines.append(f'<div class="article-index-summary">{summary}</div>')
        lines.append("</div>")
        lines.append("")
    return lines


def _build_tags_html(is_rec: bool, journal: str, keywords: list[str]) -> str:
    parts: list[str] = []
    if is_rec:
        parts.append('<span class="tag tag-rec" data-tag="⭐ 推荐阅读">⭐ 推荐阅读</span>')
    if journal:
        parts.append(f'<span class="tag tag-journal" data-tag="{_escape_attr(journal)}">{_escape_html(journal)}</span>')
    for kw in keywords:
        parts.append(f'<span class="tag tag-keyword" data-tag="{_escape_attr(kw)}">{_escape_html(kw)}</span>')
    return "".join(parts)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape_html(text).replace('"', "&quot;")


def render_wechat_markdown(
    config: AppConfig,
    categories: OrderedDict[str, list[dict[str, str]]],
) -> str:
    lines = _wechat_header(config)
    lines.append("---")
    lines.append("")
    for index, (category, articles) in enumerate(categories.items()):
        if index:
            lines.append("---")
            lines.append("")
        lines.append(f"## 关键词：{category}")
        lines.append("")
        for article in articles:
            lines.append(f"### {title(article)}")
            lines.append(f"**{value(article, 'authors', '作者信息缺失')}**")
            lines.append(f"*{publication_info(article)}*")
            lines.append(value(article, "summary", "摘要或总结缺失").replace("\n", "\n> "))
            lines.append("")
    lines.extend(
        [
            "---",
            "![扫码关注情绪和文化实验室公众号](https://emotionculturelab.wordpress.com/wp-content/uploads/2024/05/01-1621859719-843741.png)",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _lab_header(config: AppConfig) -> list[str]:
    year = config.project.year or ""
    month = config.project.month or ""
    start = config.project.start_date
    end = config.project.end_date
    if start and end:
        date_display = f"{start.replace('-', '.').removeprefix(f'{year}.')}-{end.replace('-', '.').removeprefix(f'{year}.')}"
        title_line = f"# {config.project.name} {year}.{date_display}"
    else:
        title_line = f"# {config.project.name} {year}年{month}月刊".strip()
    return [
        title_line,
        "",
        "![](https://emotionculturelab.com/wp-content/uploads/2024/09/e59bbee789874.png)",
    ]


def _wechat_header(config: AppConfig) -> list[str]:
    year = config.project.year or ""
    month = config.project.month or ""
    start = config.project.start_date
    end = config.project.end_date
    if start and end:
        date_display = f"{start.replace('-', '.').removeprefix(f'{year}.')}-{end.replace('-', '.').removeprefix(f'{year}.')}"
        title_line = f"# {config.project.name} {year}.{date_display}"
        full_url = (
            f"https://github.com/ZJU-ECLab/ECLab-News/releases/download/"
            f"v{start}_{end}/journal_{start}_{end}_lab.html"
        )
    else:
        title_line = f"# {config.project.name} {year}年{month}月刊".strip()
        full_url = config.project.wechat_full_version_url or ""
    return [
        title_line,
        "![](https://emotionculturelab.com/wp-content/uploads/2024/09/e59bbee789874.png)",
        "> 《东西情报》是**浙江大学情绪和文化实验室**所创办的、收集每周情绪心理学领域文章和最新科研进展的文献汇编。",
        "> 每一期《东西情报》把不同文章划分为了情绪、文化、面孔、声音等多个关键词，并将文章总结梳理成简短的概要，旨在让读者用短时间了解当前情绪领域的最新成果和动向。",
        "> 通过系统而高效的知识整合，《东西情报》致力于搭建连接前沿科研与公众科普的桥梁，期待能为屏幕前的你带来帮助！",
        "> **《东西情报》完整版请点击下方链接获取。**",
        f"[阅读完整版]({full_url})" if full_url else "[阅读完整版]()",
    ]


def _url_markdown(article: dict[str, str]) -> str:
    link = url(article)
    return f"[{link}]({link})" if link else "链接缺失"

