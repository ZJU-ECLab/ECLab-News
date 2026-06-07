from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import AppConfig
from .csv_io import read_articles, write_articles

_SUMMARIZE_WORKERS = 5


def summarize_csv(
    config: AppConfig,
    csv_path: str,
    force: bool = False,
    limit: int | None = None,
    retry_zero: bool = False,
) -> None:
    rows = read_articles(csv_path)
    todo_indices = [
        i for i, row in enumerate(rows)
        if _should_process_row(row, force=force, retry_zero=retry_zero)
    ]
    if limit is not None:
        todo_indices = todo_indices[:limit]
    total = len(todo_indices)
    if not total:
        log_missing_after_summarize(csv_path)
        return

    counter = [0]
    lock = threading.Lock()

    def _process(i: int) -> tuple[int, dict[str, str]]:
        row = rows[i]
        if not str(row.get("abstract", "")).strip():
            row["summary"] = "摘要缺失，无法生成自动总结。"
            row["relevant"] = ""
        else:
            summary, corrected_category, recommended = summarize_article(config, row)
            if corrected_category:
                row["category"] = corrected_category
            row["summary"] = summary
            row["relevant"] = "false" if summary.strip() == "0" else "true"
            row["recommended"] = recommended
        with lock:
            counter[0] += 1
            _print_progress("Summarizing", counter[0], total)
        return i, row

    with ThreadPoolExecutor(max_workers=_SUMMARIZE_WORKERS) as pool:
        futures = {pool.submit(_process, i): i for i in todo_indices}
        for future in as_completed(futures):
            idx, updated_row = future.result()
            with lock:
                rows[idx] = updated_row
    write_articles(rows, csv_path)

    print()
    log_missing_after_summarize(csv_path)


def summarize_article(config: AppConfig, row: dict[str, str]) -> tuple[str, str, str]:
    """Returns (summary, corrected_category, recommended)."""
    import logging
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)
    from litellm import completion

    api_key = os.getenv(config.llm.api_key_env)
    api_base = os.getenv(config.llm.api_base_env)
    model = os.getenv("LLM_MODEL") or config.llm.model
    if not api_key:
        raise RuntimeError(f"Set {config.llm.api_key_env} before summarizing articles.")

    user_prompt = config.llm.user_prompt.format(
        title=row.get("title", ""),
        journal=row.get("journal", ""),
        authors=row.get("authors", ""),
        keywords=row.get("keywords", ""),
        matched_keywords=row.get("matched_keywords", ""),
        category=row.get("category", ""),
        abstract=row.get("abstract", ""),
    )
    kwargs: dict = {
        "model": model,
        "api_key": api_key,
        "temperature": config.llm.temperature,
        "messages": [
            {"role": "system", "content": config.llm.system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if api_base:
        kwargs["api_base"] = api_base

    for attempt in range(2):
        response = completion(**kwargs)
        content = response.choices[0].message.content or ""
        result = _parse_response(content, config)
        if result is not None:
            return result
        # Ask the model to fix its output on the first failure
        if attempt == 0:
            kwargs["messages"] = kwargs["messages"] + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": "输出格式有误，请重新输出：不相关时只输出数字 0，相关时只输出合法 JSON 对象。"},
            ]

    return "0", "", ""


def _parse_response(content: str, config: AppConfig) -> tuple[str, str, str] | None:
    """Parse a JSON response from the LLM.

    Returns (summary, category, recommended) or None if the JSON is invalid
    or missing required fields.
    """
    text = content.strip()
    if text == "0":
        return "0", "", ""

    # Strip markdown code fences if the model wraps the JSON
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("```")
        ).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    relevant = str(data.get("relevant", "true")).strip().lower()
    if relevant == "false" or str(data.get("summary", "")).strip() == "0":
        return "0", "", ""

    summary = str(data.get("summary", "")).strip()
    if not summary:
        return None

    raw_categories = data.get("category", "")
    if isinstance(raw_categories, list):
        raw_categories = ", ".join(str(c) for c in raw_categories)
    category = _clean_categories(str(raw_categories), config)

    recommended = "true" if str(data.get("recommended", "")).strip().lower() == "true" else ""

    return summary, category, recommended


def _clean_categories(raw: str, config: AppConfig) -> str:
    valid = {name.casefold(): name for name in config.categories}
    chosen: list[str] = []
    for piece in raw.replace("，", ",").split(","):
        name = piece.strip()
        if not name:
            continue
        canonical = valid.get(name.casefold())
        if canonical and canonical not in chosen:
            chosen.append(canonical)
    return ", ".join(chosen)


def _should_process_row(row: dict[str, str], force: bool, retry_zero: bool) -> bool:
    existing = str(row.get("summary", "")).strip()
    return not existing or force or (retry_zero and existing == "0")


def _print_progress(label: str, current: int, total: int) -> None:
    total = max(total, 1)
    width = 28
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r{label}: [{bar}] {current}/{total}", end="", flush=True)


def log_missing_after_summarize(csv_path: str) -> None:
    rows = read_articles(csv_path)
    relevant_rows = [
        row for row in rows
        if str(row.get("relevant", "")).lower() != "false"
        and str(row.get("summary", "")).strip() != "0"
    ]
    for row in relevant_rows:
        missing = []
        for field in ("abstract", "authors", "keywords"):
            val = str(row.get(field, "")).strip()
            if not val or val in ("摘要缺失", "作者信息缺失", "关键词缺失"):
                missing.append(field)
        if missing:
            label = row.get("doi") or row.get("title") or "(unknown)"
            print(f"[missing {', '.join(missing)}] {label}")
