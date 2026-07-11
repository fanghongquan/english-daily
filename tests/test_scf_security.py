import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch

from scf import index as scf


ACCESS_KEY = "a" * 32
ORIGIN = "https://fanghongquan.github.io"


def signed_event(payload, *, timestamp=None, nonce="nonce_1234567890", origin=ORIGIN,
                 key=ACCESS_KEY, ip="203.0.113.1"):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    digest = hashlib.sha256(body.encode()).hexdigest()
    canonical = f"{timestamp}\n{nonce}\n{digest}"
    signature = hmac.new(key.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "httpMethod": "POST",
        "body": body,
        "headers": {
            "origin": origin,
            "x-app-timestamp": timestamp,
            "x-app-nonce": nonce,
            "x-app-signature": signature,
        },
        "requestContext": {"sourceIp": ip},
    }


class ScfSecurityTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {
            "APP_ACCESS_KEY": ACCESS_KEY,
            "TENCENT_SECRET_ID": "sid",
            "TENCENT_SECRET_KEY": "skey",
            "MAIMEMO_TOKEN": "maimemo-token",
        })
        self.env.start()
        self.allowed = patch.object(scf, "ALLOW_ORIGIN", ORIGIN)
        self.allowed.start()
        scf._RATE.clear()

    def tearDown(self):
        self.allowed.stop()
        self.env.stop()

    def test_valid_signature_reaches_operation(self):
        with patch.object(scf, "do_get", return_value={"lib": []}) as operation:
            response = scf.main_handler(signed_event({"op": "get", "key": "abc"}), None)
        self.assertEqual(200, response["statusCode"])
        operation.assert_called_once()

    def test_missing_signature_is_unauthorized(self):
        event = signed_event({"op": "get", "key": "abc"})
        event["headers"].pop("x-app-signature")
        self.assertEqual(401, scf.main_handler(event, None)["statusCode"])

    def test_bad_signature_is_unauthorized(self):
        event = signed_event({"op": "get", "key": "abc"})
        event["headers"]["x-app-signature"] = "0" * 64
        self.assertEqual(401, scf.main_handler(event, None)["statusCode"])

    def test_expired_signature_is_unauthorized(self):
        event = signed_event({"op": "get", "key": "abc"}, timestamp=int(time.time()) - 301)
        self.assertEqual(401, scf.main_handler(event, None)["statusCode"])

    def test_wrong_origin_is_forbidden(self):
        event = signed_event({"op": "get", "key": "abc"}, origin="https://evil.test")
        self.assertEqual(403, scf.main_handler(event, None)["statusCode"])

    def test_oversized_body_is_rejected(self):
        event = signed_event({"op": "tts", "text": "x" * 17000})
        self.assertEqual(413, scf.main_handler(event, None)["statusCode"])

    def test_preflight_requires_allowed_origin_but_not_signature(self):
        event = {"httpMethod": "OPTIONS", "headers": {"origin": ORIGIN}}
        self.assertEqual(200, scf.main_handler(event, None)["statusCode"])

    def test_rate_limit_rejects_burst(self):
        with patch.object(scf, "RATE_BURST", 1), patch.object(scf, "RATE_PER_MINUTE", 0), \
                patch.object(scf, "do_get", return_value={"lib": []}):
            first = scf.main_handler(signed_event({"op": "get", "key": "abc"}), None)
            second = scf.main_handler(signed_event({"op": "get", "key": "abc"},
                                                   nonce="nonce_abcdefghijk"), None)
        self.assertEqual(200, first["statusCode"])
        self.assertEqual(429, second["statusCode"])

    def test_maimemo_operation_is_routed(self):
        with patch.object(scf, "do_maimemo", return_value={"ok": True}) as operation:
            response = scf.main_handler(
                signed_event({"op": "maimemo", "text": "reliable"}), None
            )
        self.assertEqual(200, response["statusCode"])
        operation.assert_called_once_with("maimemo-token", "reliable")


if __name__ == "__main__":
    unittest.main()
