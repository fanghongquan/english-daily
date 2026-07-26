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
