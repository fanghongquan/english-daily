import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadingExperienceContractTest(unittest.TestCase):
    def template(self):
        return (ROOT / "template.html").read_text(encoding="utf-8")

    def test_mobile_hybrid_toolbar_and_accessibility_contract(self):
        html = self.template()
        for marker in (
            'id="read-progress"', 'role="progressbar"', 'id="mobile-float"',
            'id="mobile-play"', 'id="mobile-more"', 'id="mobile-panel"',
            'env(safe-area-inset-bottom)', '@media (max-width:640px)',
            ':focus-visible', 'prefers-reduced-motion', 'for="rate"',
            'for="voice"', "setAttribute('aria-pressed'", "lang='en-US'",
            "lang='zh-CN'",
        ):
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
