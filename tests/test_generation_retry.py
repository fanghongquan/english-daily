import copy
import json
import unittest
from unittest.mock import patch

import get_article
from tests.test_article_validation import valid_article


class TemporaryModelError(RuntimeError):
    status_code = 503


NEWS_MATERIAL = {
    "title": "Baby pangolin found by roadside, safely returned to the wild",
    "summary": "A young pangolin was rescued and released back into the wild.",
    "link": "https://news.cgtn.com/news/2026-09-16/pangolin-1QudjYN",
    "source": "CGTN",
    "published": "Thu, 17 Sep 2026 02:44:49 -0400",
}


class NewsGenerationTest(unittest.TestCase):
    def test_prompt_includes_the_news_material_and_rewrite_rules(self):
        prompt = get_article._build_prompt("2026-07-11", news=NEWS_MATERIAL)
        self.assertIn(NEWS_MATERIAL["title"], prompt)
        self.assertIn(NEWS_MATERIAL["summary"], prompt)
        self.assertIn("来源：CGTN", prompt)
        self.assertIn("不得整句照抄原文", prompt)

    def test_prompt_without_news_is_unchanged(self):
        # 回归守卫：news 默认 None 时必须完全走原来的内置主题库路径。
        prompt = get_article._build_prompt("2026-07-11")
        self.assertIn("【本篇主题（必须严格围绕它来写）】", prompt)
        self.assertNotIn("【本篇素材", prompt)
        self.assertIn(get_article._pick_topic("2026-07-11"), prompt)

    def test_gen_news_attaches_the_source_for_attribution(self):
        valid = valid_article()
        with patch.object(get_article.news_source, "pick",
                          return_value=NEWS_MATERIAL), \
                patch.object(get_article, "_call_model",
                             return_value=json.dumps(valid)):
            result = get_article.gen_news("2026-07-11")

        self.assertEqual({
            "name": "CGTN",
            "title": NEWS_MATERIAL["title"],
            "url": NEWS_MATERIAL["link"],
        }, result["source"])

    def test_gen_news_falls_back_to_the_topic_library(self):
        valid = valid_article()
        with patch.object(get_article.news_source, "pick", return_value=None), \
                patch.object(get_article, "_call_model",
                             return_value=json.dumps(valid)) as call_model:
            result = get_article.gen_news("2026-07-11")

        self.assertNotIn("source", result)
        self.assertNotIn("【本篇素材", call_model.call_args[0][0])

    def test_retrying_reuses_the_same_news_material(self):
        # 提示词在重试循环外只构建一次，重试时改写的必须是同一条新闻。
        short = copy.deepcopy(valid_article())
        for paragraph in short["paragraphs"]:
            paragraph["en"] = "Too short."
        valid = valid_article()

        with patch.object(get_article.news_source, "pick",
                          return_value=NEWS_MATERIAL) as pick, \
                patch.object(get_article, "_call_model",
                             side_effect=[json.dumps(short), json.dumps(valid)]) as call_model:
            get_article.gen_news("2026-07-11")

        self.assertEqual(1, pick.call_count)
        self.assertEqual(2, call_model.call_count)
        self.assertEqual(call_model.call_args_list[0][0][0],
                         call_model.call_args_list[1][0][0])


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
            "正文目标：约 1000 词",
            "新词目标：约 7 个",
            "句子复杂度：4 / 5",
            "理解目标：85%-90%",
            "近期趋势：可以稍微提高难度",
        ):
            self.assertIn(marker, prompt)
        self.assertNotIn("每段挑 2-3 个", prompt)
        self.assertIn("重点词总量服从后面的个人阅读难度目标", prompt)

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


if __name__ == "__main__":
    unittest.main()
