import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build
from tests.test_article_validation import valid_article


class BuildSecurityTest(unittest.TestCase):
    def test_build_escapes_script_terminators_and_dangerous_markup(self):
        data = valid_article()
        data["title"] = "safe </script><script>alert(1)</script>"
        data["paragraphs"][0]["en"] += '<img src=x onerror="alert(1)">'
        data["paragraphs"][0]["zh"] = '<img src=x onerror="alert(2)">中文'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.json"
            article.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            site = root / "docs"
            template = Path(build.__file__).with_name("template.html")
            with patch.object(build, "ROOT", root), patch.object(build, "SITE", site), \
                    patch.object(build, "TEMPLATE", template), \
                    patch.dict("os.environ", {"TTS_API_URL": 'https://example.test/a"b'}):
                output = Path(build.build(str(article)))
            page = output.read_text(encoding="utf-8")

        self.assertNotIn("</script><script>alert", page)
        self.assertIn(r"\u003c/script\u003e", page)
        self.assertNotIn('<img src=x onerror=', page)
        self.assertNotIn(r'\u003cimg src=x onerror', page.split('"zh":', 1)[0])
        self.assertIn('const TTS_API = "https://example.test/a\\\"b";', page)
        self.assertIn("Content-Security-Policy", page)

    def test_template_uses_text_content_for_chinese_translation(self):
        template = Path(build.__file__).with_name("template.html").read_text(encoding="utf-8")
        self.assertIn("zh.textContent = p.zh", template)
        self.assertNotIn("'<div class=\"zh\">'+p.zh", template)


if __name__ == "__main__":
    unittest.main()
