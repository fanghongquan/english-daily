import json
import io
import os
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest.mock import patch

import profile_client


TOKEN = "t" * 32


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def valid_response(**overrides):
    profile = {
        "profile_version": 1,
        "target_mode": "balanced",
        "ability_score": 54.5,
        "observation_count": 4,
        "target_words": 1000,
        "target_new_words": 7,
        "sentence_level": 4,
        "target_comprehension": "85%-90%",
        "trend": "harder",
        "updated_at": "2026-07-28T00:00:00Z",
    }
    profile.update(overrides)
    return json.dumps({"profile": profile}).encode()


class ProfileClientTest(unittest.TestCase):
    def test_fetches_and_validates_profile(self):
        with patch("urllib.request.urlopen",
                   return_value=FakeResponse(valid_response())) as request:
            profile = profile_client.fetch_profile(
                "https://profile.test", TOKEN)
        self.assertEqual(1000, profile["target_words"])
        self.assertEqual("harder", profile["trend"])
        req = request.call_args.args[0]
        self.assertEqual(TOKEN, req.headers["X-profile-token"])
        self.assertEqual(10, request.call_args.kwargs["timeout"])
        self.assertEqual({"op": "profile_get"},
                         json.loads(req.data.decode()))

    def test_missing_environment_returns_independent_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            first = profile_client.load_profile_from_env()
            second = profile_client.load_profile_from_env()
        first["target_words"] = 1100
        self.assertEqual(900, second["target_words"])

    def test_network_and_format_failures_fall_back_without_raising(self):
        failures = (
            urllib.error.URLError("offline"),
            TimeoutError("slow"),
        )
        for failure in failures:
            warning = io.StringIO()
            with self.subTest(failure=type(failure).__name__), \
                    patch("urllib.request.urlopen", side_effect=failure), \
                    redirect_stderr(warning):
                self.assertEqual(
                    900,
                    profile_client.fetch_profile(
                        "https://profile.test", TOKEN)["target_words"])

    def test_fallback_warning_is_sanitized(self):
        warning = io.StringIO()
        with patch("urllib.request.urlopen",
                   return_value=FakeResponse(b"private-invalid-body")), \
                redirect_stderr(warning):
            profile = profile_client.fetch_profile(
                "https://private-profile.test/path", TOKEN)
        output = warning.getvalue()
        self.assertEqual(900, profile["target_words"])
        self.assertIn("默认平衡档案", output)
        self.assertNotIn(TOKEN, output)
        self.assertNotIn("private-profile.test", output)
        self.assertNotIn("private-invalid-body", output)

        malformed = (
            b"not-json",
            json.dumps({"profile": []}).encode(),
            valid_response(target_words=2000),
            valid_response(target_new_words=20),
            valid_response(sentence_level=9),
            valid_response(trend="unknown"),
        )
        for body in malformed:
            ignored_warning = io.StringIO()
            with self.subTest(body=body[:40]), \
                    patch("urllib.request.urlopen",
                          return_value=FakeResponse(body)), \
                    redirect_stderr(ignored_warning):
                self.assertEqual(
                    900,
                    profile_client.fetch_profile(
                        "https://profile.test", TOKEN)["target_words"])


if __name__ == "__main__":
    unittest.main()
