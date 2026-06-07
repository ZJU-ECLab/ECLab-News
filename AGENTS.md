# AGENTS.md

## Project Purpose

Automates the Emotion and Culture Lab monthly literature journal.
Collects article metadata from free scholarly APIs (Crossref, PubMed, OpenAlex,
Semantic Scholar, Scopus), enriches missing fields, uses an LLM to generate
Chinese summaries from abstracts, and renders Markdown/HTML reports.

## Main Workflow

1. `eclab-news detect-sources`
   Probes each configured journal against PubMed and Crossref to determine the
   best source per journal. Writes results to `[search.journal_sources]` in
   `config.toml`. Run once after changing the journal list.

2. `eclab-news collect`
   Fetches articles per journal using the configured source (PubMed or Crossref,
   per `journal_sources`). Applies structural filters (journal, date, supplemental),
   deduplicates, enriches missing fields from multiple APIs (PubMed → Crossref →
   Springer → OpenAlex → Semantic Scholar → PubMed title search → OpenAlex title
   search → Scopus → HTML landing-page fallback), then runs a strict
   relevance filter. Writes CSV.

3. `eclab-news summarize`
   Reads the CSV and asks an LLM to judge relevance and generate Chinese
   summaries from titles/abstracts. Secrets come from environment variables.

4. `eclab-news render`
   Generates Markdown.
   - `--variant lab`: linked index with tabs to switch between keyword and journal
     views, recommended articles section, and detailed article records. Supports
     interactive filtering in HTML output via sidebar categories.
   - `--variant wechat`: compact format without extra blank lines after headings.

5. `eclab-news pandoc`
   Converts lab Markdown to HTML using pandoc with the template and theme in
   `pandoc/`. Reads accent color from config.

`eclab-news all` runs all steps in order.

## Important Files

- `config.toml`: project, search, category, LLM prompt, and pandoc config.
- `src/cli.py`: CLI entry points and per-journal collection routing.
- `src/processing.py`: filtering pipeline and multi-source enrichment.
- `src/render.py`: Markdown rendering (lab + wechat variants).
- `src/summarize.py`: LLM summarization.
- `src/config.py`: config dataclasses and loader.
- `src/models.py`: `Article` dataclass and CSV columns.
- `src/csv_io.py`: CSV read/write.
- `src/articles.py`: article grouping and display helpers.
- `src/journals.py`: journal name/ISSN matching and supplemental checks.
- `src/category.py`: keyword-based category inference.
- `src/relevance.py`: basic psychology-relevance heuristic.
- `src/sources/`: API clients (crossref, pubmed, openalex, semanticscholar, scopus, springer, common) and `abstract_fallback.py` (HTML landing-page abstract recovery).
- `pandoc/template.html`: pandoc HTML template with TOC and watermark.
- `pandoc/theme.css`: CSS theme (accent-color-driven).

## Contributor Rules

- Do not put API keys in config files or source code.
- Prefer free APIs.
- Keep incomplete article rows unless the user explicitly asks to drop them.
- WeChat Markdown should stay compact; avoid blank lines after headings.
- Lab Markdown should be spacious and include links from the index to details.
- Avoid pandas/numpy; this project uses the standard library `csv` module.
- When changing CSV columns, update `CSV_COLUMNS` in `src/models.py`.
