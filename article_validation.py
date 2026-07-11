"""Validation and safe normalization for generated article data."""
import copy
import datetime
import html
import re
from html.parser import HTMLParser


class ArticleValidationError(ValueError):
    """Raised when generated article data does not satisfy the site contract."""


class _KeywordSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.allowed_depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "span" and values.get("class") == "kw":
            ipa = values.get("data-ipa")
            definition = values.get("data-def")
            if ipa is not None and definition is not None:
                self.parts.append(
                    '<span class="kw" data-ipa="%s" data-def="%s">'
                    % (html.escape(ipa, quote=True), html.escape(definition, quote=True))
                )
                self.allowed_depth += 1
                return
        self.parts.append(html.escape(f"<{tag}>"))

    def handle_endtag(self, tag):
        if tag == "span" and self.allowed_depth:
            self.parts.append("</span>")
            self.allowed_depth -= 1
        else:
            self.parts.append(html.escape(f"</{tag}>"))

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")


def _sanitize_fragment(value: str) -> str:
    parser = _KeywordSanitizer()
    parser.feed(value)
    parser.close()
    if parser.allowed_depth:
        parser.parts.extend("</span>" for _ in range(parser.allowed_depth))
    return "".join(parser.parts)


def _require_text(obj, key, context="article"):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ArticleValidationError(f"{context}.{key} must be non-empty text")


def prepare_article(data: dict, expected_date: str | None = None) -> dict:
    """Return a deep-copied, validated article with sanitized paragraph HTML."""
    if not isinstance(data, dict):
        raise ArticleValidationError("article must be an object")
    result = copy.deepcopy(data)
    for key in ("date", "level", "title", "title_zh", "intro_zh"):
        _require_text(result, key)
    try:
        datetime.date.fromisoformat(result["date"])
    except ValueError as exc:
        raise ArticleValidationError("article.date must be an ISO date") from exc
    if expected_date and result["date"] != expected_date:
        raise ArticleValidationError(
            f"article.date {result['date']!r} does not match {expected_date!r}"
        )

    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list) or not 7 <= len(paragraphs) <= 12:
        raise ArticleValidationError("article.paragraphs must contain 7 to 12 items")
    for index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            raise ArticleValidationError(f"paragraphs[{index}] must be an object")
        _require_text(paragraph, "en", f"paragraphs[{index}]")
        _require_text(paragraph, "zh", f"paragraphs[{index}]")
        paragraph["en"] = _sanitize_fragment(paragraph["en"])

    plain_english = " ".join(
        html.unescape(re.sub(r"<[^>]+>", " ", paragraph["en"]))
        for paragraph in paragraphs
    )
    word_count = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", plain_english))
    if not 500 <= word_count <= 1600:
        raise ArticleValidationError(
            f"article word count must be between 500 and 1600; got {word_count}"
        )

    questions = result.get("questions", [])
    if questions:
        if not isinstance(questions, list) or not 3 <= len(questions) <= 4:
            raise ArticleValidationError("article.questions must contain 3 to 4 items")
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                raise ArticleValidationError(f"questions[{index}] must be an object")
            qkey = "q" if "q" in question else "question"
            _require_text(question, qkey, f"questions[{index}]")
            options = question.get("options")
            if (not isinstance(options, list) or len(options) != 4
                    or any(not isinstance(option, str) or not option.strip()
                           for option in options)):
                raise ArticleValidationError(
                    f"questions[{index}].options must contain four non-empty strings"
                )
            answer = question.get("answer")
            if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer <= 3:
                raise ArticleValidationError(f"questions[{index}].answer must be 0 through 3")
    return result
