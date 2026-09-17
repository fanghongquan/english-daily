import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import news_source


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Baby pangolin found by roadside, safely returned to the wild</title>
    <link>https://example.com/pangolin</link>
    <description>&lt;p&gt;A young pangolin was &lt;b&gt;rescued&lt;/b&gt; and released.&lt;/p&gt;</description>
    <pubDate>Thu, 17 Sep 2026 02:44:49 -0400</pubDate>
  </item>
  <item>
    <title>How porcelain shaped a small town</title>
    <link>https://example.com/porcelain</link>
    <description>Kilns have burned here for centuries.</description>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Scientists map a coral reef's recovery</title>
    <link href="https://example.org/coral"/>
    <summary>Divers counted three times as many fish as a decade ago.</summary>
    <updated>2026-09-17T00:00:00Z</updated>
  </entry>
</feed>"""


class FakeResponse:
    """与 test_profile_client.FakeResponse 同形。"""

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def fake_opener(mapping):
    """按 URL 返回预设响应；未列出的 URL 模拟网络失败。"""
    def opener(request, timeout=None):
        url = request.full_url
        if url not in mapping:
            raise urllib.error.URLError("unreachable")
        return FakeResponse(mapping[url])
    return opener


def rss_item(title, link, description="", published=""):
    return (
        "<item><title>%s</title><link>%s</link>"
        "<description>%s</description><pubDate>%s</pubDate></item>"
        % (title, link, description, published)
    )


def rss_with(*items):
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>%s</channel></rss>'
        % "".join(items)
    ).encode("utf-8")


class ParseTest(unittest.TestCase):
    def test_parses_rss_2_0_and_strips_html_from_summary(self):
        items = news_source._parse(RSS.encode("utf-8"), "Sixth Tone")
        self.assertEqual(2, len(items))
        first = items[0]
        self.assertEqual(
            "Baby pangolin found by roadside, safely returned to the wild",
            first["title"])
        self.assertEqual("https://example.com/pangolin", first["link"])
        self.assertEqual("Sixth Tone", first["source"])
        self.assertEqual("Thu, 17 Sep 2026 02:44:49 -0400", first["published"])
        self.assertNotIn("<p>", first["summary"])
        self.assertNotIn("<b>", first["summary"])
        self.assertIn("rescued", first["summary"])

    def test_parses_atom_entries(self):
        items = news_source._parse(ATOM.encode("utf-8"), "Phys.org")
        self.assertEqual(1, len(items))
        self.assertEqual("https://example.org/coral", items[0]["link"])
        self.assertIn("three times as many fish", items[0]["summary"])
        self.assertEqual("2026-09-17T00:00:00Z", items[0]["published"])

    def test_strips_bare_urls_left_behind_by_tag_removal(self):
        # Sixth Tone 的 description 是 <a href="..."> 且 URL 里带未转义空格，
        # 剥掉标签后会把 URL 文字留在摘要里。
        raw = rss_with(rss_item(
            "A title",
            "https://example.com/x",
            '&lt;a href="https://www.example.com/news/1019036/Big Story"&gt;'
            '&lt;/a&gt;The actual summary text.'))
        items = news_source._parse(raw, "Sixth Tone")
        self.assertNotIn("http", items[0]["summary"])
        self.assertIn("The actual summary text.", items[0]["summary"])

    def test_truncates_summary_to_the_limit(self):
        raw = rss_with(rss_item("A title", "https://example.com/x", "word " * 400))
        items = news_source._parse(raw, "NPR")
        self.assertLessEqual(len(items[0]["summary"]), news_source.SUMMARY_LIMIT)

    def test_skips_items_without_a_title_or_link(self):
        raw = rss_with(
            rss_item("", "https://example.com/no-title"),
            rss_item("Has a title but no link", ""),
            rss_item("Good item", "https://example.com/good"),
        )
        items = news_source._parse(raw, "NPR")
        self.assertEqual(["Good item"], [item["title"] for item in items])


class BlocklistTest(unittest.TestCase):
    def test_blocks_negative_event_headlines(self):
        for title in (
            "Three injured in wildfire on Spain's Costa del Sol",
            "9th woman found dead in South Africa, adding to fears of serial killer",
            "Nearly 100 Chinese nationals missing in Nepal's disaster",
            "People's houses are collapsing into the ocean",
            "Key highway reopens amid all-out mudslide rescue effort",
            "Nearly 600 people have died in crashes, investigation finds",
        ):
            with self.subTest(title=title):
                self.assertTrue(news_source._is_blocked(title))

    def test_blocks_political_headlines(self):
        for title in (
            "Arabic version of \"Classic Quotes Cited by Xi Jinping\" launches",
            "Retracing the Long March: Luding Bridge and the Red Army trail",
            "Why the world needs BRICS: From economic weight to global growth",
            "Israeli forces raze Palestinian olive trees",
            "Simple messaging can help restore trust in US elections",
            "Beijing Xiangshan Forum plays key role in global multilateralism",
        ):
            with self.subTest(title=title):
                self.assertTrue(news_source._is_blocked(title))

    def test_blocks_generic_news_roundups(self):
        for title in ("Morning news brief", "Daily briefing: what to know",
                      "The week in photos"):
            with self.subTest(title=title):
                self.assertTrue(news_source._is_blocked(title))

    def test_keeps_ordinary_science_and_culture_headlines(self):
        for title in (
            "Baby pangolin found by roadside, safely returned to the wild",
            "Why do Panda birthdays matter?",
            "Scientists turn seawater into fresh water without harmful brine",
            "Mobile trap transports 92 antiprotons by road",
            "A 240-million-year-old fossil just changed the dinosaur timeline",
            "Smelling chocolate helped men complete more reps",
            "World Lake Day: Healthy lakes need healthy ecosystems",
        ):
            with self.subTest(title=title):
                self.assertFalse(news_source._is_blocked(title))

    def test_word_boundaries_prevent_substring_matches(self):
        # 这些词都包含词表条目的字面片段，但都不是坏消息。
        for title in (
            "Deadline extended for the design competition",
            "Software engineers are rewriting the rules",
            "New diesel engine cuts emissions sharply",
            "Warm weather brings early cherry blossoms",
        ):
            with self.subTest(title=title):
                self.assertFalse(news_source._is_blocked(title))

    def test_matches_inflected_forms(self):
        # 词表写的是词根，靠后缀规则覆盖屈折形式 —— 曾经漏过这两个。
        for title in (
            "People's houses are collapsing into the ocean",
            "Beijing forum highlights multilateralism",
        ):
            with self.subTest(title=title):
                self.assertTrue(news_source._is_blocked(title))

    def test_does_not_match_the_summary_so_science_summaries_survive(self):
        # 只看标题：摘要里的 "crashed"/"dead" 在科普文里描述的是天文与生物现象。
        # 回归守卫 —— 曾经因为连摘要一起匹配而误杀大量 ScienceDaily 内容。
        raw = rss_with(rss_item(
            "Venus may have swallowed its own moon",
            "https://example.com/venus",
            "The moon crashed into the planet and the surface died out."))
        items = news_source._parse(raw, "ScienceDaily")
        self.assertEqual(1, len(items))
        self.assertFalse(news_source._is_blocked(items[0]["title"]))

    def test_blocks_empty_titles(self):
        self.assertTrue(news_source._is_blocked(""))


class FetchTest(unittest.TestCase):
    def test_fetch_collects_items_from_every_feed(self):
        feeds = [("Sixth Tone", "https://a.test/rss"), ("NPR", "https://b.test/rss")]
        opener = fake_opener({
            "https://a.test/rss": RSS.encode("utf-8"),
            "https://b.test/rss": ATOM.encode("utf-8"),
        })
        with patch.object(news_source, "FEEDS", feeds), \
                patch("urllib.request.urlopen", side_effect=opener):
            items = news_source.fetch()
        self.assertEqual(3, len(items))
        self.assertEqual({"Sixth Tone", "NPR"}, {item["source"] for item in items})

    def test_one_dead_feed_does_not_lose_the_others(self):
        feeds = [("Dead", "https://dead.test/rss"), ("NPR", "https://b.test/rss")]
        opener = fake_opener({"https://b.test/rss": ATOM.encode("utf-8")})
        with patch.object(news_source, "FEEDS", feeds), \
                patch("urllib.request.urlopen", side_effect=opener):
            items = news_source.fetch()
        self.assertEqual(1, len(items))
        self.assertEqual("NPR", items[0]["source"])

    def test_network_failures_return_an_empty_list_without_raising(self):
        for error in (urllib.error.URLError("blocked"), TimeoutError("timed out"),
                      ValueError("boom")):
            with self.subTest(error=type(error).__name__):
                with patch.object(news_source, "FEEDS",
                                  [("X", "https://x.test/rss")]), \
                        patch("urllib.request.urlopen", side_effect=error):
                    self.assertEqual([], news_source.fetch())

    def test_all_configured_feeds_use_http_or_https(self):
        self.assertTrue(news_source.FEEDS)
        for name, url in news_source.FEEDS:
            with self.subTest(url=url):
                self.assertTrue(name.strip())
                self.assertTrue(url.startswith("https://")
                                or url.startswith("http://"))


class PickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "articles").mkdir()

    def _write_article(self, date, url):
        (self.root / "articles" / f"{date}.json").write_text(
            json.dumps({"source": {"name": "X", "title": "T", "url": url}}),
            encoding="utf-8")

    def _pick(self, body, date="2026-09-18"):
        with patch.object(news_source, "ROOT", self.root), \
                patch.object(news_source, "FEEDS", [("X", "https://x.test/rss")]), \
                patch("urllib.request.urlopen", side_effect=fake_opener(
                    {"https://x.test/rss": body})):
            return news_source.pick(date)

    def test_picks_a_usable_item(self):
        picked = self._pick(RSS.encode("utf-8"))
        self.assertIn(picked["title"], (
            "Baby pangolin found by roadside, safely returned to the wild",
            "How porcelain shaped a small town"))

    def test_same_date_picks_the_same_item(self):
        body = RSS.encode("utf-8")
        self.assertEqual(self._pick(body), self._pick(body))

    def test_returns_none_when_every_item_is_filtered_out(self):
        body = rss_with(
            rss_item("Three injured in wildfire", "https://example.com/1"),
            rss_item("Morning news brief", "https://example.com/2"))
        self.assertIsNone(self._pick(body))

    def test_skips_links_used_by_recent_articles(self):
        self._write_article("2026-09-17", "https://example.com/pangolin")
        picked = self._pick(RSS.encode("utf-8"))
        self.assertEqual("How porcelain shaped a small town", picked["title"])

    def test_returns_none_when_all_candidates_were_already_used(self):
        self._write_article("2026-09-17", "https://example.com/pangolin")
        self._write_article("2026-09-16", "https://example.com/porcelain")
        self.assertIsNone(self._pick(RSS.encode("utf-8")))

    def test_malformed_xml_and_empty_feeds_return_none_without_raising(self):
        for body in (b"<html>not xml at all",
                     b'<?xml version="1.0"?><rss><channel></channel></rss>'):
            with self.subTest(body=body[:24]):
                self.assertIsNone(self._pick(body))

    def test_survives_a_corrupt_article_file_while_deduplicating(self):
        (self.root / "articles" / "2026-09-17.json").write_text(
            "{not valid json", encoding="utf-8")
        picked = self._pick(RSS.encode("utf-8"))
        self.assertIsNotNone(picked)


if __name__ == "__main__":
    unittest.main()
