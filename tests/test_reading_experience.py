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

    def test_local_reading_progress_and_resume_contract(self):
        html = self.template()
        for marker in (
            "englishDaily:progress:", "function loadProgress", "function saveProgress",
            "requestAnimationFrame", 'id="continue-reading"', "继续阅读", "从头开始",
            "ratio>=.92", "lastParagraph", "aria-valuenow", "scrollTo",
        ):
            self.assertIn(marker, html)

    def test_paragraph_narration_contract(self):
        html = self.template()
        for marker in (
            "朗读本段", "data-paragraph", "activeParagraph", "function setSpeakingState",
            "aria-current", "nearestParagraph()", "startParagraph", "mobile-play",
        ):
            self.assertIn(marker, html)

    def test_automatic_vocabulary_list_contract(self):
        html = self.template()
        for marker in (
            'id="vocab-sec"', 'id="vocab-filter"', "function collectVocabulary",
            "toLowerCase()", "entry.count++", "vocab-play", "vocab-add",
            "doAdd(entry.word)",
        ):
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
