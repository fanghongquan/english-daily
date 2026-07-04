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

    def test_template_uses_double_click_vocab_only(self):
        self.assert_double_click_vocab_only(self.read("template.html"))

    def test_latest_built_page_uses_double_click_vocab_only(self):
        self.assert_double_click_vocab_only(self.read("docs/2026-07-03.html"))


if __name__ == "__main__":
    unittest.main()
