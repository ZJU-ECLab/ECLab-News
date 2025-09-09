import os
import pandas as pd

year = 2025
month = 8

editor_in_chief = ["主编1", "主编2"]


def clean_text(text):
    if isinstance(text, str):
        return (
            text.replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("\n", " ")
            .strip()
        )
    return text


def load_articles_from_files(directory="files"):
    if not os.path.exists(directory):
        print(f"Error: The '{directory}' directory was not found.")
        print("Please create it and place your Excel files inside.")
        return []

    all_articles = []
    for filename in os.listdir(directory):
        if filename.endswith(".xlsx"):
            filepath = os.path.join(directory, filename)
            try:
                df = pd.read_excel(filepath)
                for col in df.select_dtypes(include=["object"]).columns:
                    df[col] = df[col].astype(str).apply(clean_text)
                all_articles.extend(df.to_dict(orient="records"))
            except Exception as e:
                print(f"Error processing file {filename}: {e}")
    return all_articles


def categorize_articles(articles):
    categories = {}
    processed_titles = set()

    for article in articles:
        title = article.get("title", "")
        if not title or title in processed_titles:
            continue
        processed_titles.add(title)

        article_categories = [c.strip() for c in article.get("category", "").split(",")]
        for category in article_categories:
            if not category:
                continue
            capitalized_category = category.capitalize()
            if capitalized_category not in categories:
                categories[capitalized_category] = []
            categories[capitalized_category].append(article)
    return categories


def generate_markdown_content(categories, year, month, chief_editors):
    md_lines = []

    # 1. Header
    md_lines.append(f"# 东西情报 {year}年{month}月刊")
    md_lines.append("")
    md_lines.append(
        "![](https://emotionculturelab.com/wp-content/uploads/2024/09/e59bbee789874.png)"
    )
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("[阅读完整版]()")
    md_lines.append("")

    # 2. Article Sections
    for i, category in enumerate(categories.keys()):
        articles = categories[category]
        md_lines.append(f"## 关键词：{category}")
        md_lines.append("")

        for j, article in enumerate(articles):
            if j > 0:
                md_lines.append(">")

            md_lines.append(f"> ### {article.get('title', 'No Title')}")
            md_lines.append(">")
            md_lines.append(f"> **{article.get('authors', 'No Authors')}**")
            md_lines.append(">")
            md_lines.append(f"> *{article.get('journal', 'No Journal')}*")
            md_lines.append(">")

            summary = article.get("summary", "No Summary").replace("\n", "\n> ")
            md_lines.append(f"> {summary}")

        if i < len(categories) - 1:
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

    # 3. Footer
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(
        "![扫码关注情绪和文化实验室公众号](https://emotionculturelab.wordpress.com/wp-content/uploads/2024/05/01-1621859719-843741.png)"
    )
    md_lines.append("")

    if chief_editors:
        editors_name = "、".join(chief_editors)
        md_lines.append(f'<p align="right">本期主编：{editors_name}</p>')

    return "\n".join(md_lines)


if __name__ == "__main__":
    articles = load_articles_from_files()
    if articles:
        categorized_data = categorize_articles(articles)
        markdown_output = generate_markdown_content(
            categorized_data, year, month, editor_in_chief
        )

        output_filename = f"journal_{year}_{month}.md"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(markdown_output)

        print(f"Successfully generated markdown file: '{output_filename}'")
