from adapters.edgar.documents import html_to_text, submission_documents

SUBMISSION = """<SEC-DOCUMENT>0001065280-26-000211.txt
<DOCUMENT>
<TYPE>8-K
<SEQUENCE>1
<FILENAME>nflx-20260716.htm
<TEXT>
<html><head><style>p {color: red}</style></head><body><p>Item 2.02</p></body></html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-99.1
<SEQUENCE>2
<FILENAME>ex991_q226.htm
<TEXT>
<html><body><p>Revenue&nbsp;grew 13%</p><table><tr><td>Q3'26</td><td>$12,860</td></tr></table>
<script>var x = 1;</script></body></html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>GRAPHIC
<SEQUENCE>3
<FILENAME>logo.jpg
<TEXT>
begin 644 logo.jpg
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


def test_text_documents_with_types() -> None:
    documents = submission_documents(SUBMISSION)
    assert [(d.type, d.filename) for d in documents] == [
        ("8-K", "nflx-20260716.htm"),
        ("EX-99.1", "ex991_q226.htm"),
    ]  # картинка пропущена
    assert documents[0].text == "Item 2.02"  # стили не попадают в текст
    assert documents[1].text == "Revenue grew 13%\nQ3'26 | $12,860"


def test_html_to_text_unescapes_and_drops_blank_lines() -> None:
    assert html_to_text("<div>A &amp; B</div>\n\n\n<div>C</div>") == "A & B\n\nC"


def test_submission_without_documents() -> None:
    assert submission_documents("no documents here") == []
