"""Документы подачи EDGAR из полного текста (`<accession>.txt`): пресс-релизы 8-K (EX-99.x).

Полный текст подачи надёжнее имён файлов: тип документа указан в теге <TYPE>, а имена приложений
у компаний разные (у JPM нет файла с «ex991» в имени). Картинки и XBRL пропускаются.
"""

import html
import re
from dataclasses import dataclass

DOCUMENT = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.DOTALL | re.IGNORECASE)
FIELD = re.compile(r"<(TYPE|FILENAME)>([^\n<]*)", re.IGNORECASE)
TEXT = re.compile(r"<TEXT>(.*?)</TEXT>", re.DOTALL | re.IGNORECASE)
TEXT_EXTENSIONS = (".htm", ".html", ".txt")

HIDDEN = re.compile(r"<(script|style|head)\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
LINE_BREAK = re.compile(r"<(br|/p|/div|/tr|/h[1-6]|/li|/table)\b[^>]*>", re.IGNORECASE)
CELL = re.compile(r"</t[dh]\s*>", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"[ \t\r\f\v ]+")
BLANK_LINES = re.compile(r"\n\s*\n+")


@dataclass(frozen=True)
class FilingDocument:
    type: str  # EX-99.1, 8-K …
    filename: str
    text: str  # без разметки


def submission_documents(submission: str) -> list[FilingDocument]:
    """Текстовые документы подачи в порядке следования."""
    documents = []
    for block in DOCUMENT.findall(submission):
        fields = {name.upper(): value.strip() for name, value in FIELD.findall(block)}
        filename = fields.get("FILENAME", "")
        body = TEXT.search(block)
        if body is None or not filename.lower().endswith(TEXT_EXTENSIONS):
            continue
        documents.append(
            FilingDocument(fields.get("TYPE", "").upper(), filename, html_to_text(body.group(1)))
        )
    return documents


def html_to_text(markup: str) -> str:
    """HTML → читаемый текст: строки таблиц — строками, ячейки — через « | »."""
    text = HIDDEN.sub(" ", markup)
    text = CELL.sub(" | ", text)
    text = LINE_BREAK.sub("\n", text)
    text = html.unescape(TAG.sub(" ", text))
    lines = (SPACES.sub(" ", line).strip(" |") for line in text.split("\n"))
    return BLANK_LINES.sub("\n\n", "\n".join(line for line in lines)).strip()
