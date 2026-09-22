import copy
import json
import re
import unittest
from unittest.mock import patch

import get_article
from article_validation import body_word_count
from tests.test_article_validation import valid_article


class TemporaryModelError(RuntimeError):
    status_code = 503


class GenerationRetryTest(unittest.TestCase):
    def test_prompt_states_the_hard_minimum_word_count(self):
        self.assertIn("绝不能少于 500 词", get_article._build_prompt("2026-07-11"))

    def test_prompt_uses_derived_learner_targets(self):
        profile = {
            "target_words": 1000,
            "target_new_words": 7,
            "sentence_level": 4,
            "target_comprehension": "85%-90%",
            "trend": "harder",
        }
        prompt = get_article._build_prompt("2026-07-11", profile=profile)
        for marker in (
            "新词目标：约 7 个",
            "句子复杂度：4 / 5",
            "理解目标：85%-90%",
            "近期趋势：可以稍微提高难度",
        ):
            self.assertIn(marker, prompt)
        self.assertNotIn("每段挑 2-3 个", prompt)
        self.assertIn("重点词总量服从后面的个人阅读难度目标", prompt)

    def test_prompt_word_count_does_not_follow_the_profile(self):
        """字数只由固定规则决定，不随档案漂移。

        服务端曾按能力分返回 700-1100 的 target_words。旧提示词把它插进正文
        目标，于是模型同时收到「约 1000 词」和「严格控制在 500-580 词」两条
        矛盾指令，字数就会往中间飘。字数是用户自己定的，不该被档案改回去。
        """
        base = {
            "target_new_words": 6, "sentence_level": 3,
            "target_comprehension": "85%-90%", "trend": "stable",
        }
        low = get_article._build_prompt(
            "2026-07-11", profile=dict(base, target_words=500))
        high = get_article._build_prompt(
            "2026-07-11", profile=dict(base, target_words=1000))
        self.assertEqual(low, high)
        self.assertIn("500-580", low)
        self.assertNotIn("约 1000 词", high)

    def test_retries_when_generated_article_fails_validation(self):
        short = copy.deepcopy(valid_article())
        for paragraph in short["paragraphs"]:
            paragraph["en"] = "Too short."
        valid = valid_article()

        with patch.object(
            get_article,
            "_call_model",
            side_effect=[json.dumps(short), json.dumps(valid)],
        ) as call_model:
            result = get_article.gen_ai("2026-07-11")

        self.assertEqual(2, call_model.call_count)
        self.assertEqual(valid["title"], result["title"])

    def test_retries_when_model_returns_non_object_json(self):
        valid = valid_article()

        with patch.object(
            get_article,
            "_call_model",
            side_effect=[json.dumps([]), json.dumps(valid)],
        ) as call_model:
            result = get_article.gen_ai("2026-07-11")

        self.assertEqual(2, call_model.call_count)
        self.assertEqual(valid["title"], result["title"])

    def test_retries_temporary_model_api_errors(self):
        valid = valid_article()

        with patch.object(
            get_article,
            "_call_model",
            side_effect=[TemporaryModelError("temporary outage"), json.dumps(valid)],
        ) as call_model:
            result = get_article.gen_ai("2026-07-11")

        self.assertEqual(2, call_model.call_count)
        self.assertEqual(valid["title"], result["title"])


def overlong_article(extra_per_paragraph: int = 40):
    """夹具本身 574 词，卡在 580 以内；加词造一篇明确超长的。"""
    data = valid_article()
    for paragraph in data["paragraphs"]:
        paragraph["en"] += " " + " ".join(["extra"] * extra_per_paragraph)
    return data


class WordCountGuardTest(unittest.TestCase):
    def test_retries_when_the_article_is_longer_than_the_range(self):
        """字数越界要重试，不能像 2026-09-11~17 那样连着一周出 810-1058 词。"""
        overlong = overlong_article()
        valid = valid_article()
        self.assertGreater(body_word_count(overlong["paragraphs"]), 580)

        with patch.object(get_article, "_call_model",
                          side_effect=[json.dumps(overlong),
                                       json.dumps(valid)]) as call_model:
            result = get_article.gen_ai("2026-07-11")

        self.assertEqual(2, call_model.call_count)
        self.assertEqual(valid["title"], result["title"])
        self.assertTrue(500 <= body_word_count(result["paragraphs"]) <= 580)

    def test_keeps_the_last_article_when_every_attempt_misses_the_range(self):
        """四轮都超长时收下最后一篇——断更比文章长一点更糟。

        这是刻意的取舍：宁可用一篇 850 词的文章，也不要当天没有文章。
        """
        overlong = overlong_article()

        with patch.object(get_article, "_call_model",
                          return_value=json.dumps(overlong)) as call_model:
            result = get_article.gen_ai("2026-07-11")

        self.assertEqual(4, call_model.call_count)
        self.assertGreater(body_word_count(result["paragraphs"]), 580)

    def test_counts_words_without_mistaking_html_tags_for_words(self):
        """口径守卫：<span class="kw"> 不能算成 3 个词。

        直接对带标签的正文数词，一篇 533 词的文章会数出 587，
        于是明明合规的文章被误判成超长、反复重试。
        """
        data = valid_article()
        raw = " ".join(p["en"] for p in data["paragraphs"])
        tagged = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", raw))
        self.assertEqual(574, body_word_count(data["paragraphs"]))
        self.assertGreater(tagged, body_word_count(data["paragraphs"]))


if __name__ == "__main__":
    unittest.main()
