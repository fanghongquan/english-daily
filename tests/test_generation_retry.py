import copy
import json
import unittest
from unittest.mock import patch

import get_article
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
            "正文目标：约 1000 词",
            "新词目标：约 7 个",
            "句子复杂度：4 / 5",
            "理解目标：85%-90%",
            "近期趋势：可以稍微提高难度",
        ):
            self.assertIn(marker, prompt)

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
