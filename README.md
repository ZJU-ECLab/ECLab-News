# ECLab News

情绪和文化实验室每月文献汇编自动化流水线。

## 流程

1. `collect` — 从 Crossref / PubMed 收集文章元数据，过滤、补充缺失字段，写入 CSV
2. `summarize` — 调用 LLM 判断相关性并生成中文摘要
3. `render` — 生成 Markdown 报告（lab 版 / 微信版）
4. `pandoc` — 将 lab Markdown 转换为带主题的 HTML
5. `site-export` — 将一期导出为网站用的 JSON（含摘要）
6. `manifest` — 扫描所有期刊 JSON，生成网站索引 `manifest.json`

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

# 导出网站 JSON 并重建索引
uv run eclab-news site-export --config config.toml --csv data/articles.csv \
  --start 2026-06-01 --end 2026-06-07 --output site/issues/2026-06-01_2026-06-07.json
uv run eclab-news manifest --config config.toml --issues-dir site/issues --output site/manifest.json
```

## 网站（ZJU-ECLab.github.io）

公开网站是独立仓库 `ZJU-ECLab/ZJU-ECLab.github.io`，组织默认 Pages 站点，
地址 <https://zju-eclab.github.io>。它是数据驱动的单页应用：所有期刊共用同一套
模板（`index.html` + `assets/app.js` + `assets/style.css`），**不为每期生成 HTML**。
公开 JSON 由 CloudBase 对象存储提供：

- `journal/v1/issues/<期次>.json`：单期完整内容
- `journal/v1/manifest.json`：首页使用的轻量期次索引

**发布流程**：CI 下载现有的轻量 manifest，将新一期元数据合并进去，先上传
issue JSON，再上传 manifest。只有当网站、issue 和 manifest 都能从生产地址读取后，
才向网站仓库发送事件，由网站仓库发布 Discussion 和钉钉通知。

## GitHub Actions

添加仓库 Secrets：

- `LLM_API_KEY`、`LLM_API_BASE`（必需），可选 `LLM_MODEL`、`NCBI_API_KEY`、`S2_API_KEY`、`SCOPUS_API_KEY`
- `CLOUDBASE_API_KEY`：CloudBase 环境的发布密钥，用于上传 issue 和 manifest。
- `SITE_DEPLOY_TOKEN`：对 `ZJU-ECLab.github.io` 具有 `contents:write` 权限的
  细粒度 Personal Access Token，仅用于在发布验证成功后发送 announcement dispatch。

发布 Release 或手动触发 workflow 时，自动运行全流程、上传报告、发布 CloudBase
数据，并在生产验证成功后通知读者。JSON 同时保存为 Release/Actions 归档。
