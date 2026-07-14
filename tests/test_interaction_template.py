from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InteractionTemplateTest(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def assert_double_click_vocab_only(self, html):
        self.assertIn('id="sel-add"', html)
        self.assertNotIn('id="sel-play"', html)
        self.assertNotIn('id="sel-translate"', html)
        self.assertNotIn('id="transbox"', html)
        self.assertNotIn("-webkit-touch-callout:none", html)
        self.assertNotIn("user-select:none", html)
        self.assertIn("dblclick", html)
        self.assertNotIn("pointerdown", html)
        self.assertNotIn("pointerup", html)
        self.assertNotIn("function translate", html)

    def assert_phrase_collection(self, html):
        self.assertIn('id="sel-phrase"', html)
        self.assertIn('id="phrase-add"', html)
        self.assertIn('id="phrase-cancel"', html)
        self.assertIn("function enterPhraseMode", html)
        self.assertIn("function selectPhraseEnd", html)
        self.assertIn("function phraseFromTokens", html)
        self.assertIn("start.closest('.en')!==end.closest('.en')", html)
        self.assertIn("selected.length<2", html)
        self.assertIn("selected.length>10", html)
        self.assertIn("replace(/^[^A-Za-z]+|[^A-Za-z]+$/g", html)
        self.assertIn("短语需在同一段内", html)
        self.assertIn("短语最多 10 个词", html)
        self.assertIn("function exitPhraseMode", html)
        self.assertIn("doAdd(selText)", html)
        self.assertIn("env(safe-area-inset-bottom)", html)
        self.assertNotIn("window.getSelection", html)

    def test_template_uses_double_click_vocab_only(self):
        self.assert_double_click_vocab_only(self.read("template.html"))

    def test_template_supports_phrase_collection(self):
        self.assert_phrase_collection(self.read("template.html"))

    def test_latest_built_page_supports_word_and_phrase_collection(self):
        html = self.read("docs/2026-07-13.html")
        self.assert_double_click_vocab_only(html)
        self.assert_phrase_collection(html)


if __name__ == "__main__":
    unittest.main()
