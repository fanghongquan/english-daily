import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendAuthContractTest(unittest.TestCase):
    def test_template_signs_protected_requests_and_clears_rejected_key(self):
        template = (ROOT / "template.html").read_text(encoding="utf-8")
        for marker in (
            "APP_ACCESS_KEY",
            "crypto.subtle.importKey",
            "crypto.subtle.digest",
            "HMAC",
            "X-App-Timestamp",
            "X-App-Nonce",
            "X-App-Signature",
            "protectedFetch",
        ):
            self.assertIn(marker, template)
        self.assertIn("localStorage.removeItem('APP_ACCESS_KEY')", template)
        self.assertIn("protectedFetch({text,voice})", template)
        self.assertIn("protectedFetch({op:'maimemo',text})", template)

    def test_automatic_feedback_sync_does_not_prompt_for_access_key(self):
        template = (ROOT / "template.html").read_text(encoding="utf-8")
        for marker in (
            "function storedAccessKey",
            "async function syncLearningFeedback(interactive=false)",
            "if(!interactive&&!storedAccessKey())",
            "protectedFetch(payload,{allowPrompt:interactive})",
        ):
            self.assertIn(marker, template)

    def test_saving_access_key_retries_pending_feedback(self):
        template = (ROOT / "template.html").read_text(encoding="utf-8")
        handler = template[
            template.index("document.getElementById('access-key').onclick"):
            template.index("function toggleMore")]
        self.assertIn("scheduleLearningFeedbackSync()", handler)


if __name__ == "__main__":
    unittest.main()
