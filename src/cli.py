from __future__ import annotations

import copy
import re
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path

import httpx

from .config import AppConfig, load_config
from .csv_io import deduplicate_articles, write_article_rows
from .journals import issns_for_journal
from .models import Article
from .processing import process_articles
from .render import render_markdown
from .sources.crossref import collect_crossref
from .sources.pubmed import collect_pubmed
from .summarize import summarize_csv

_PANDOC_CSS = Path(__file__).parent.parent / "pandoc" / "theme.css"
_PANDOC_TEMPLATE = Path(__file__).parent.parent / "pandoc" / "template.html"


def render_pandoc(md_path: str, output_dir: Path, stem: str, config: AppConfig | None = None) -> None:
    """Convert a lab Markdown file to HTML via pandoc."""
    html_out = output_dir / f"{stem}.html"
    raw = Path(md_path).read_text(encoding="utf-8")
    # Strip leading h1 and logo img — both are rendered by the template header
    stripped = re.sub(r"^#[^#][^\n]*\n", "", raw, count=1)
    stripped = re.sub(r"^!\[.*?\]\(.*?\)\n", "", stripped, flags=re.MULTILINE, count=1)

    project_name = config.project.name if config else "东西情报"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})_(\d{4})-(\d{2})-(\d{2})", stem)
    if m:
        y1, m1, d1, y2, m2, d2 = m.groups()
        display_title = f"{project_name} {y1}.{m1}.{d1}-{m2}.{d2}" if y1 == y2 else f"{project_name} {y1}.{m1}.{d1}-{y2}.{m2}.{d2}"
    else:
        mo = re.search(r"(\d{4})_(\d{2})", stem)
        display_title = f"{project_name} {mo.group(1)}.{mo.group(2)}" if mo else project_name

    accent_color = config.pandoc.accent_color if config else "#8b3a3a"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write(stripped)
        tmp_path = tmp.name
    try:
        subprocess.run(
            [
                "pandoc", tmp_path,
                "--standalone",
                "--toc", "--toc-depth=3",
                f"--css={_PANDOC_CSS}",
                f"--template={_PANDOC_TEMPLATE}",
                "--metadata", f"title={display_title}",
                "--metadata", f"accent-color={accent_color}",
                "-o", str(html_out),
            ],
            check=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    css_text = _PANDOC_CSS.read_text(encoding="utf-8")
    html_text = html_out.read_text(encoding="utf-8")
    html_text = re.sub(
        r'<link rel="stylesheet" href="[^"]*theme\.css" />\s*',
        "<style>\n" + css_text + "\n</style>\n",
        html_text,
    )
    html_out.write_text(html_text, encoding="utf-8")
    print(f"Wrote HTML to {html_out}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="eclab-news")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = _base_parser(subparsers, "collect")
    collect_parser.add_argument("--start", required=True)
    collect_parser.add_argument("--end", required=True)
    collect_parser.add_argument("--output", required=True)
    collect_parser.add_argument("--max-results", type=int, default=500)

    summarize_parser = _base_parser(subparsers, "summarize")
    summarize_parser.add_argument("--csv", required=True)
    summarize_parser.add_argument("--force", action="store_true")
    summarize_parser.add_argument("--retry-zero", action="store_true")
    summarize_parser.add_argument("--limit", type=int)

    render_parser = _base_parser(subparsers, "render")
    render_parser.add_argument("--csv", required=True)
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--variant", choices=["lab", "wechat"], default="lab")
    render_parser.add_argument("--include-irrelevant", action="store_true")

    pandoc_parser = _base_parser(subparsers, "pandoc")
    pandoc_parser.add_argument("--md", required=True)
    pandoc_parser.add_argument("--output-dir", default="reports")

    all_parser = _base_parser(subparsers, "all")
    all_parser.add_argument("--start", required=True)
    all_parser.add_argument("--end", required=True)
    all_parser.add_argument("--output-dir", default=".")
    all_parser.add_argument("--max-results", type=int, default=500)
    all_parser.add_argument("--force-summary", action="store_true")
    all_parser.add_argument("--accent-color", default="", help="Override accent color (auto-generated if blank)")

    detect_parser = _base_parser(subparsers, "detect-sources")
    detect_parser.add_argument("--lookback-months", type=int, default=6)

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "collect":
        articles = collect_articles(config, _parse_date(args.start), _parse_date(args.end), args.max_results)
        write_article_rows(articles, args.output)
        print(f"Wrote {len(articles)} articles to {args.output}")
    elif args.command == "summarize":
        summarize_csv(config, args.csv, force=args.force, limit=args.limit, retry_zero=args.retry_zero)
        print(f"Updated summaries in {args.csv}")
    elif args.command == "render":
        render_markdown(config, args.csv, args.output, args.variant, args.include_irrelevant)
        print(f"Wrote {args.variant} Markdown to {args.output}")
    elif args.command == "pandoc":
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        render_pandoc(args.md, output_dir, Path(args.md).stem, config)
    elif args.command == "all":
        output_dir = Path(args.output_dir)
        start_date = _parse_date(args.start)
        end_date = _parse_date(args.end)
        config.project.year = start_date.year
        config.project.month = start_date.month
        config.project.start_date = args.start
        config.project.end_date = args.end
        # Use provided accent color or generate a random one
        config.pandoc.accent_color = args.accent_color or _random_accent_color()
        date_suffix = f"{args.start}_{args.end}"
        csv_path = output_dir / "data" / f"articles_{date_suffix}.csv"
        lab_md = output_dir / "reports" / f"journal_{date_suffix}_lab.md"
        wechat_md = output_dir / "reports" / f"journal_{date_suffix}_wechat.md"
        reports_dir = output_dir / "reports"
        articles = collect_articles(config, start_date, end_date, args.max_results)
        write_article_rows(articles, csv_path)
        summarize_csv(config, str(csv_path), force=args.force_summary, retry_zero=True)
        render_markdown(config, str(csv_path), str(lab_md), "lab")
        render_markdown(config, str(csv_path), str(wechat_md), "wechat")
        render_pandoc(str(lab_md), reports_dir, lab_md.stem, config)
        print(f"Wrote {csv_path}, {lab_md}, {wechat_md}, and pandoc outputs")
    elif args.command == "detect-sources":
        detect_sources(config, args.config, args.lookback_months)


def _base_parser(subparsers, name: str):
    import argparse
    parser = subparsers.add_parser(name)
    parser.add_argument("--config", default="config.toml")
    return parser


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _random_accent_color() -> str:
    """Generate a muted, comfortable accent color using HSL."""
    import random
    h = random.randint(0, 359)
    # Avoid yellow-green range (80-140°) which has poor contrast on white
    if 80 <= h <= 140:
        h = (h + 80) % 360
    return f"hsl({h}, 40%, 48%)"


def collect_articles(config: AppConfig, start: date, end: date, max_results: int) -> list[Article]:
    journal_sources = config.search.journal_sources
    default_sources = config.search.sources

    pubmed_journals = [j for j in config.search.journals
                       if "pubmed" in journal_sources.get(j, default_sources)]
    crossref_journals = [j for j in config.search.journals
                         if "crossref" in journal_sources.get(j, default_sources)]

    articles: list[Article] = []

    if pubmed_journals:
        sub = _sub_config(config, pubmed_journals)
        pm = collect_pubmed(sub, start, end, max_results=max_results)
        articles.extend(pm)
        print(f"PubMed: {len(pm)} articles from {len(pubmed_journals)} journals")

    if crossref_journals:
        sub = _sub_config(config, crossref_journals)
        cr = collect_crossref(sub, start, end, max_results=max_results)
        articles.extend(cr)
        print(f"Crossref: {len(cr)} articles from {len(crossref_journals)} journals")

    articles = deduplicate_articles(articles)
    print(f"Total after dedup: {len(articles)} — filtering and enriching...")
    articles = process_articles(config, start=start, end=end, articles=articles)
    print(f"Final: {len(articles)} articles")
    return articles[:max_results]


def _sub_config(config: AppConfig, journals: list[str]) -> AppConfig:
    sub = copy.copy(config)
    sub.search = copy.copy(config.search)
    sub.search.journals = journals
    return sub


def detect_sources(config: AppConfig, config_path: str, lookback_months: int = 6) -> None:
    """Probe each journal in PubMed and Crossref; update [search.journal_sources] in config.toml."""
    end = date.today()
    start = date(end.year if end.month > lookback_months else end.year - 1,
                 (end.month - lookback_months - 1) % 12 + 1, 1)

    results: dict[str, list[str]] = {}
    ua = f"eclab-news/0.1 (mailto:{config.search.email})" if config.search.email else "eclab-news/0.1"
    client = httpx.Client(timeout=20, headers={"User-Agent": ua})
    total = len(config.search.journals)
    try:
        for i, journal in enumerate(config.search.journals, 1):
            print(f"\rDetecting sources: {i}/{total} — {journal[:50]}", end="", flush=True)
            issns = issns_for_journal(journal, config.search.journal_issns)
            sources: list[str] = []

            # PubMed check via ISSN
            issn_term = " OR ".join(f'"{issn}"[ISSN]' for issn in issns) if issns else f'"{journal}"[Journal]'
            try:
                r = client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": f"({issn_term}) AND {start}:{end}[dp]", "retmax": "1", "retmode": "json"},
                )
                if int(r.json().get("esearchresult", {}).get("count", 0)) > 0:
                    sources.append("pubmed")
            except Exception:
                pass

            # Crossref check via ISSN
            issn_filter = "".join(f",issn:{issn}" for issn in issns)
            try:
                params = {"filter": f"type:journal-article,from-pub-date:{start},until-pub-date:{end}{issn_filter}", "rows": "1"}
                if config.search.email:
                    params["mailto"] = config.search.email
                r = client.get("https://api.crossref.org/works", params=params)
                if r.json().get("message", {}).get("items"):
                    sources.append("crossref")
            except Exception:
                pass

            results[journal] = sources or ["crossref"]
    finally:
        client.close()
    print()

    # Write [search.journal_sources] to config.toml
    raw = Path(config_path).read_text(encoding="utf-8")
    raw = re.sub(r"\[search\.journal_sources\].*?(?=\n\[|\Z)", "", raw, flags=re.DOTALL).rstrip() + "\n"
    lines = ["\n[search.journal_sources]"]
    for journal, srcs in sorted(results.items()):
        key = f'"{journal}"' if any(c in journal for c in ' ,&()') else journal
        lines.append(f"{key} = {str(srcs).replace(chr(39), chr(34))}")
    Path(config_path).write_text(raw + "\n".join(lines) + "\n", encoding="utf-8")

    pm_only = sum(1 for s in results.values() if s == ["pubmed"])
    cr_only = sum(1 for s in results.values() if s == ["crossref"])
    both = sum(1 for s in results.values() if len(s) == 2)
    print(f"Updated {config_path}: PubMed-only={pm_only}, Crossref-only={cr_only}, both={both}")


if __name__ == "__main__":
    main()
