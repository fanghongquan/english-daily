import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import daily
import push_feishu
from delivery_state import is_pushed
from tests.test_article_validation import valid_article


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def args(**overrides):
    values = dict(source="ai", date="2026-07-11", use_latest=False,
                  no_push=False, no_audio=False, force=False)
    values.update(overrides)
    return argparse.Namespace(**values)


class FeishuPushTest(unittest.TestCase):
    def test_push_accepts_business_success(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse('{"code":0,"msg":"ok"}')):
            push_feishu.push("https://example.test", "", {})

    def test_push_raises_on_business_error(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse('{"code":19001,"msg":"bad"}')):
            with self.assertRaisesRegex(RuntimeError, "19001"):
                push_feishu.push("https://example.test", "", {})

    def test_push_raises_on_malformed_response(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse("not-json")):
            with self.assertRaisesRegex(RuntimeError, "JSON"):
                push_feishu.push("https://example.test", "", {})


class DailyDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "articles").mkdir()
        article = valid_article()
        (self.root / "articles" / "2026-07-11.json").write_text(
            json.dumps(article, ensure_ascii=False), encoding="utf-8"
        )
        self.env = patch.dict("os.environ", {
            "SITE_BASE_URL": "https://example.test",
            "FEISHU_WEBHOOK": "https://hook.test",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_failed_push_does_not_mark_delivery(self):
        def fail(*_):
            raise RuntimeError("push failed")

        with self.assertRaisesRegex(RuntimeError, "push failed"):
            daily.run(args(), root=self.root, build_fn=lambda _: None, push_fn=fail)
        self.assertFalse(is_pushed(self.root / "state", "2026-07-11"))

    def test_successful_push_marks_and_duplicate_skips(self):
        calls = []

        def record(*values):
            calls.append(values)

        daily.run(args(), root=self.root, build_fn=lambda _: None, push_fn=record)
        daily.run(args(), root=self.root, build_fn=lambda _: None, push_fn=record)
        self.assertEqual(1, len(calls))
        self.assertTrue(is_pushed(self.root / "state", "2026-07-11"))

    def test_no_push_does_not_mark_delivery(self):
        daily.run(args(no_push=True), root=self.root, build_fn=lambda _: None)
        self.assertFalse(is_pushed(self.root / "state", "2026-07-11"))

    def test_generation_failure_does_not_fallback_to_old_article(self):
        with self.assertRaisesRegex(RuntimeError, "generation failed"):
            daily.run(args(date="2026-07-12"), root=self.root,
                      build_fn=lambda _: None,
                      generate_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("generation failed")))


if __name__ == "__main__":
    unittest.main()
