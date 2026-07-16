# AGENTS.md

## Project Purpose

Automates the Emotion and Culture Lab monthly literature journal.
Collects article metadata from free scholarly APIs (Crossref, PubMed, OpenAlex,
Semantic Scholar, Scopus), enriches missing fields, uses an LLM to generate
Chinese summaries from abstracts, and renders Markdown reports.

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

5. `eclab-news site-export`
   Writes one weekly issue as a normalized JSON file (`<start>_<end>.json`) for
   the website. Contains issue metadata (label, title, date range, accent color)
   plus a flat list of articles including abstracts. Keyword/journal grouping is
   derived client-side by the site, so the JSON stays a single article list.

6. `eclab-news manifest`
   Scans a directory of issue JSON files and writes `manifest.json` (all issues
   newest-first with lightweight metadata only). Used to rebuild the site index
   after publishing a new issue.

`eclab-news all` runs collect → summarize → render → site-export → manifest in
order, writing the JSON to `site/issues/` and `site/manifest.json`.

## Website (ZJU-ECLab.github.io)

The public site is a separate repo, `ZJU-ECLab/ZJU-ECLab.github.io` (the org's
default GitHub Pages site at <https://zju-eclab.github.io>). The weekly journal
is a data-driven single-page app served at `/journal/` — one shared template
renders every issue, so **no per-week HTML is generated**:

- `journal/index.html` + `assets/style.css` (ported from `pandoc/theme.css`) + `assets/app.js`.
- CloudBase object storage serves `journal/v1/manifest.json` and
  `journal/v1/issues/<label>.json`. The SPA fetches them directly from its
  production CDN domain.
- Hash routes: `#/` (landing, grouped by year) and `#/issue/<start>_<end>`.

This repo's `.github/workflows/release.yml` runs the pipeline, downloads only
the lightweight CloudBase manifest, merges the new issue metadata with
`eclab-news manifest-update`, uploads the issue first and the manifest last,
then verifies the production URLs. CI authenticates with the environment's
server-side `CLOUDBASE_API_KEY`. A newly published label dispatches the site
repo's announcement workflow through `SITE_DEPLOY_TOKEN`. The WeChat
Markdown's "完整版" link points to
`zju-eclab.github.io/journal/#/issue/<label>`.

## Important Files

- `config.toml`: project, search, category, and LLM prompt config.
- `src/cli.py`: CLI entry points and per-journal collection routing.
- `src/processing.py`: filtering pipeline and multi-source enrichment.
- `src/render.py`: Markdown rendering (lab + wechat variants).
- `src/summarize.py`: LLM summarization.
- `src/site_export.py`: issue JSON export + manifest builder for the website.
- `src/config.py`: config dataclasses and loader.
- `src/models.py`: `Article` dataclass and CSV columns.
- `src/csv_io.py`: CSV read/write.
- `src/articles.py`: article grouping and display helpers.
- `src/journals.py`: journal name/ISSN matching and supplemental checks.
- `src/category.py`: keyword-based category inference.
- `src/relevance.py`: basic psychology-relevance heuristic.
- `src/sources/`: API clients (crossref, pubmed, openalex, semanticscholar, scopus, springer, common) and `abstract_fallback.py` (HTML landing-page abstract recovery).

## Contributor Rules

- Do not put API keys in config files or source code.
- Prefer free APIs.
- Keep incomplete article rows unless the user explicitly asks to drop them.
- WeChat Markdown should stay compact; avoid blank lines after headings.
- Avoid pandas/numpy; this project uses the standard library `csv` module.
- When changing CSV columns, update `CSV_COLUMNS` in `src/models.py`.
