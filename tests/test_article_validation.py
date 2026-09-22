import unittest

from article_validation import ArticleValidationError, prepare_article


def valid_article():
    paragraphs = []
    for i in range(7):
        words = " ".join(["useful"] * 80)
        paragraphs.append({
            "en": f'Paragraph {i} {words} <span class="kw" data-ipa="test" data-def="测试">word</span>.',
            "zh": f"第{i + 1}段翻译",
        })
    return {
        "date": "2026-07-11",
        "level": "CET-4",
        "title": "A Useful Test Article",
        "title_zh": "测试文章",
        "intro_zh": "本文用于测试。",
        "paragraphs": paragraphs,
        "questions": [{
            "q": "What is this article for?",
            "options": ["Testing", "Cooking", "Travel", "Music"],
            "answer": 0,
            "explain": "文章用于测试。",
        }] * 3,
    }


class ArticleValidationTest(unittest.TestCase):
    def test_prepare_article_accepts_valid_data_without_mutating_input(self):
        data = valid_article()
        clean = prepare_article(data, expected_date="2026-07-11")
        self.assertEqual(data, clean)
        self.assertIsNot(data, clean)

    def test_prepare_article_rejects_wrong_date(self):
        data = valid_article()
        data["date"] = "2026-07-10"
        with self.assertRaisesRegex(ArticleValidationError, "date"):
            prepare_article(data, expected_date="2026-07-11")

    def test_prepare_article_rejects_invalid_question_answer(self):
        data = valid_article()
        data["questions"][0]["answer"] = 4
        with self.assertRaisesRegex(ArticleValidationError, "answer"):
            prepare_article(data, expected_date=data["date"])

    def test_prepare_article_rejects_too_short_article(self):
        data = valid_article()
        for paragraph in data["paragraphs"]:
            paragraph["en"] = "Too short."
        with self.assertRaisesRegex(ArticleValidationError, "word count"):
            prepare_article(data, expected_date=data["date"])

    def test_prepare_article_corrects_word_count_claim_in_intro(self):
        # valid_article() 的正文固定是 574 词，模型写的 900 应被改成真实值
        data = valid_article()
        data["intro_zh"] = "本文约 900 词，用于测试。"
        clean = prepare_article(data, expected_date=data["date"])
        self.assertEqual("本文约 574 词，用于测试。", clean["intro_zh"])

    def test_prepare_article_leaves_other_word_mentions_alone(self):
        for intro in (
            "本文用于测试，含 6 个重点词。",
            "这是一篇 CET-4 难度的文章。",
            "共 9 个自然段，围绕测试展开。",
        ):
            with self.subTest(intro=intro):
                data = valid_article()
                data["intro_zh"] = intro
                clean = prepare_article(data, expected_date=data["date"])
                self.assertEqual(intro, clean["intro_zh"])

    def test_prepare_article_removes_event_handlers_and_escapes_unknown_tags(self):
        data = valid_article()
        data["paragraphs"][0]["en"] = (
            '<span class="kw" data-ipa="x" data-def="y" onclick="bad()">word</span>'
            '<img src=x onerror=bad()> ' + " ".join(["safe"] * 80)
        )
        clean = prepare_article(data, expected_date=data["date"])
        text = clean["paragraphs"][0]["en"]
        self.assertNotIn("onclick", text)
        self.assertNotIn("onerror", text)
        self.assertNotIn("<img", text)
        self.assertIn("&lt;img", text)
        self.assertIn('class="kw"', text)


if __name__ == "__main__":
    unittest.main()
