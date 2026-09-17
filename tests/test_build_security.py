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

    def test_build_escapes_untrusted_news_source_fields(self):
        # 新闻标题与来源名是外部抓来的，属于不可信输入。
        data = valid_article()
        data["source"] = {
            "name": "CGTN",
            "title": "safe </script><script>alert(1)</script>",
            "url": "https://example.test/a",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / "article.json"
            article.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            template = Path(build.__file__).with_name("template.html")
            with patch.object(build, "ROOT", root), \
                    patch.object(build, "SITE", root / "docs"), \
                    patch.object(build, "TEMPLATE", template):
                page = Path(build.build(str(article))).read_text(encoding="utf-8")

        self.assertNotIn("</script><script>alert", page)
        # 转义后的形态应当出现在页面里，证明确实序列化了而不是被丢掉
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("alert(1)", page)      # 字段确实进了页面，不是被丢弃
        self.assertIn("CGTN", page)

    def test_template_uses_text_content_for_chinese_translation(self):
        template = Path(build.__file__).with_name("template.html").read_text(encoding="utf-8")
        self.assertIn("zh.textContent = p.zh", template)
        self.assertNotIn("'<div class=\"zh\">'+p.zh", template)

    def test_template_renders_the_news_source_without_inner_html(self):
        template = Path(build.__file__).with_name("template.html").read_text(encoding="utf-8")
        self.assertIn("link.textContent=src.name", template)
        self.assertNotIn("innerHTML", template.split("const src=ARTICLE.source", 1)[1]
                         .split("})();", 1)[0])
        # 后端已校验 scheme，前端再挡一次，非法就退化成纯文本不生成链接。
        self.assertIn("u.protocol==='http:'||u.protocol==='https:'", template)


if __name__ == "__main__":
    unittest.main()
