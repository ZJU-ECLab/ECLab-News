# ECLab News

情绪和文化实验室每月文献汇编自动化流水线。

## 流程

1. `collect` — 从 Crossref / PubMed 收集文章元数据，过滤、补充缺失字段，写入 CSV
2. `summarize` — 调用 LLM 判断相关性并生成中文摘要
3. `render` — 生成 Markdown 报告（lab 版 / 微信版）
4. `pandoc` — 将 lab Markdown 转换为带主题的 HTML

## 环境变量

```bash
export LLM_API_KEY="..."
export LLM_API_BASE="https://your-endpoint/v1"
export LLM_MODEL="openai/mimo"
# 可选
export NCBI_API_KEY="..."      # 提升 PubMed 速率限制
export SCOPUS_API_KEY="..."    # Scopus 摘要补充
```

## 运行

```bash
# 检测各期刊最优数据源（首次运行或期刊列表变更后）
uv run eclab-news detect-sources --config config.toml

# 一键全流程
uv run eclab-news all --config config.toml --start 2026-06-01 --end 2026-06-07

# 或分步执行
uv run eclab-news collect --config config.toml --start 2026-06-01 --end 2026-06-07 --output data/articles.csv
uv run eclab-news summarize --config config.toml --csv data/articles.csv
uv run eclab-news render --config config.toml --csv data/articles.csv --output reports/journal_lab.md --variant lab
uv run eclab-news render --config config.toml --csv data/articles.csv --output reports/journal_wechat.md --variant wechat
uv run eclab-news pandoc --config config.toml --md reports/journal_lab.md --output-dir reports
```

## GitHub Actions

添加仓库 Secrets：`LLM_API_KEY`、`LLM_API_BASE`，可选 `LLM_MODEL`、`NCBI_API_KEY`。

发布 Release 或手动触发 workflow 时，自动运行全流程并上传报告。
