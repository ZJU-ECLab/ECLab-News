from proces import full_angle_to_half_angle
import os
import pandas as pd

year = 2024
month = 0

editor_in_chief = ["Shuoan Li, Undergraduate, 2022", "Feiyu Zhang, Undergraduate, 2022"]

editors = []


def escape_special_char(string):
    return (
        string.replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("~", "\\~")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("_", "\\_")
    )


def escape(input):
    if isinstance(input, str):
        return escape_special_char(input)
    if isinstance(input, list):
        return [escape(i) for i in input]
    if isinstance(input, dict):
        output_dict = {}
        for k, v in input.items():
            if k != "summary" and isinstance(v, str):
                v = (
                    full_angle_to_half_angle(v)
                    .replace("’", "'")
                    .replace("‘", "'")
                    .replace("“", '"')
                    .replace("”", '"')
                    .replace("–", "-")
                )
            output_dict[k] = escape(v)
        return output_dict
    return input


for file in os.listdir("files"):
    if file.endswith(".xlsx"):
        editor_info = file[:-5]
        
        try:
            df = pd.read_excel(os.path.join("files", file))
            articles = df.to_dict(orient='records')
            editor_data = {
                'editor': editor_info,
                'article': {str(i): articles[i] for i in range(len(articles))}
            }
            editors.append(escape(editor_data))
        except Exception as e:
            print(f"Error loading file {file}: {e}")

associate_editor = []
journals = []
categories = {}
for editor in editors:
    associate_editor.append(
        editor["editor"]
    )
    for key in editor["article"]:
        article = editor["article"][key]
        journal = article["journal"]
        if journal not in journals:
            journals.append(journal)
        given_categories = [c.strip() for c in article["category"].split(",")]
        for category in given_categories:
            category = category.capitalize()
            if category not in categories:
                categories[category] = []
            categories[category].append(article)

print(
    """\\documentclass{eclab-beamer}

\\usepackage{soul}

\\title{\\sffamily 东西情报}
"""
    + "\\subtitle{\\sffamily "
    + str(year)
    + "年"
    + str(month)
    + "月刊}"
)


print(
    """
\\begin{document}

\\setbeamercolor{background canvas}{bg=Titlebg}
\\begin{frame}
  \\titlepage
\\end{frame}
\\setbeamercolor{background canvas}{bg=}

\\begin{frame}{\\sffamily Editor Board}

  \\begin{itemize}

    \\item \\sffamily Editor-in-Chief

      \\begin{itemize}
"""
)

for chief in editor_in_chief:
    print("\\item " + chief)

print(
    """
      \\end{itemize}

    \\item \\sffamily Associate Editor

      \\begin{itemize}
"""
)

for aeditor in associate_editor:
    print("\\item " + aeditor)

print(
    """
      \\end{itemize}

    \\item \\sffamily Consulting Editor
      \\begin{itemize}
        \\item \\sffamily Xia Fang, PhD, Professor
      \\end{itemize}

  \\end{itemize}

\\end{frame}

\\begin{frame}[allowframebreaks]{\\sffamily Journal List}
  \\begin{itemize}\\centering
"""
)

for journal in journals:
    print("\\item " + journal)

print(
    """
  \\end{itemize}
\\end{frame}

\\begin{frame}[allowframebreaks]{\\sffamily 卷首语}

\\begin{itemize}
"""
)

for category in categories:
    print("\\item " + category + "研究更新了" + str(len(categories[category])) + "篇")
    print("\\begin{enumerate}")
    for article in categories[category]:
        print(
            "\\item \\href{"
            + article["doi"]
            + "}{\\color{blue} \\ul{"
            + article["title"]
            + "}}\\vspace{.01\\textheight}"
        )
        print(
            "\n\\footnotesize{" + article["authors"] + "}\n\n\\vspace{.01\\textheight}"
        )
        print(article["summary"])
        print("\n\\vspace{.01\\textheight}")
    print("\\end{enumerate}")
print(
    """
\\end{itemize}
\\end{frame}

"""
)

generated_articles = []
for category in categories:
    for article in categories[category]:
        if article in generated_articles:
            continue
        print(
            "\\begin{frame}[allowframebreaks]{\\color{black} \\normalsize{\\ul{"
            + category
            + "}} \\hfill"
        )
        print("\\begin{tabular}{r}")
        print("\\textit{" + article["journal"] + ", " + article["publish"] + "}\\\\")
        print(
            "\\href{"
            + article["doi"]
            + "}{\\color{blue} \\footnotesize{\\ul{\\textit{"
            + article["doi"]
            + "}}}}"
        )
        print("\\end{tabular}}\n")
        print("\\textbf{\\Large{" + article["title"] + "}}\n\n\\vspace{1mm}")
        print(article["authors"])
        print("\n\\hspace*{\\fill}\n")
        print("\n\\textbf{Abstract:}")
        print(article["abstract"])
        if "keywords" in article and article["keywords"] != "":
            print("\n\\vspace{.01\\textheight}\\textbf{Keywords:} " + article["keywords"])
        print("\\end{frame}")
        generated_articles.append(article)

print("\\end{document}")
