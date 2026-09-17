#!/usr/bin/env python3
"""从 RSS 源抓取近期新闻，挑一条作为文章素材。

容错策略与 profile_client.py 一致：**任何失败都不抛出**，返回 None 让调用方
回退到内置主题库，保证每日推送不断更。

选源原则（2026-09 实测）：
  - 优先专题栏目而非综合头条。CGTN 的 culture/nature 分栏 RSS 直接绕开了它的
    评论/时政内容，比抓回来再过滤干净得多。
  - 只收本机可达的源。本机不可达的源（见下）会让「本机无法验证」变成长期负担。
  - 实测后砍掉的源：
      * 人民网英文 —— RSS 是 Opinions 评论版，头条全是时政评论
      * 环球时报英文 —— 同类问题
      * Ecns（中新社英文）—— 幸存内容仍以经贸合作、论坛、官方活动为主，且有一条
        涉疆涉藏的宣传稿标题毫无信号、词表拦不住。整体取向与本项目的「社会文化」
        定位不符，属于源级别的取舍，不是词表能修的。
      * CGTN business —— 贡献的多是宏观金融与展会通稿（"yuan loans increase by
        10.44 trillion"、"Online Survey on the 2026 CIFTIS"），可读性差。
      * CBS News —— 头条两条是车祸死亡与连环杀手，犯罪新闻占比过高
      * BBC/卫报/Google News/AP/半岛 —— 本机 21 秒静默超时（网络封锁特征，非
        对方宕机）
      * China Daily —— RSS 全线 404，已停用
"""
import datetime
import glob
import html
import json
import random
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent

# (来源名, RSS 地址)。来源名会作为出处署名写进文章 JSON。
FEEDS = [
    ("Sixth Tone", "https://www.sixthtone.com/rss"),
    ("CGTN", "https://www.cgtn.com/subscribe/rss/section/culture.xml"),
    ("CGTN", "https://www.cgtn.com/subscribe/rss/section/nature.xml"),
    ("ScienceDaily", "https://www.sciencedaily.com/rss/all.xml"),
    ("Phys.org", "https://phys.org/rss-feed/"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
]

USER_AGENT = "Mozilla/5.0 (compatible; EnglishDaily/1.0)"
PER_FEED_LIMIT = 30
SUMMARY_LIMIT = 400


# ---- 词表：只收「事件性」的坏消息，不收「话题性」的中性词 ----------------------
# 刻意不收录 cancer / disease / 医疗 这类中性话题词：它们大量出现在正常科普里，
# 误杀代价大于收益，基调交给提示词里的「积极正向」要求去约束。
#
# 表里写**词根**，匹配时自动补常见后缀（见 _SUFFIX）。所以写 "sanction" 就同时
# 覆盖 sanctions，"multilateral" 覆盖 multilateralism。若不这么做，词表会静默
# 漏掉所有屈折形式 —— 实测漏过 "collapsing" 和 "multilateralism"。
#
# 以 e 结尾的动词去 e 加 ing 的形式（collapsing）不符合上面的规则，需要把去 e
# 的词根一起列上（"collapse" 与 "collaps" 并列）。
NEGATIVE_WORDS = (
    # 暴力与死亡
    "kill", "dead", "death", "die", "died", "dying", "murder", "homicide",
    "suicide", "shoot", "gunman", "gunmen", "stab", "stabbed", "massacre",
    "autopsy", "corpse", "victim", "fatal", "fatality", "fatalit", "wound",
    "injure", "injur", "injuring", "injury",
    # 灾害与事故
    "earthquake", "quake", "flood", "wildfire", "hurricane", "typhoon",
    "tornado", "tsunami", "landslide", "mudslide", "drought",
    "erupt", "eruption", "crash", "derail", "explosion", "explode",
    "blast", "collapse", "collaps", "evacuate", "evacuat", "evacuation",
    "trapped", "rescue", "rescu", "missing", "debris", "wreckage", "rubble",
    # 冲突
    "war", "wartime", "missile", "militant", "airstrike", "troop", "soldier",
    "combat", "ceasefire", "invasion", "artillery", "shelling", "bomb",
    "hostage", "refugee", "raze", "offensive",
    # 犯罪与司法
    "arrest", "convict", "conviction", "guilty", "prison", "jail",
    "sentence", "sentenc", "indict", "fraud", "scam", "scammer", "theft",
    "robbery", "robber", "burglar", "suspect", "prosecut", "lawsuit",
    "sue", "sued",
    "trial", "smuggl", "traffick", "crisis", "ransom", "kidnap",
    "kidnapped", "abduct",
    # 其他明确负面
    "abuse", "abused", "assault", "harass", "bully", "bullied",
    "outbreak", "epidemic", "pandemic", "contamination", "layoff",
    "bankrupt", "devastat", "tragic", "deadly", "brutal", "shocking",
    "disturbing", "flesh-eating",
    # 忧虑框架的标题（实测漏过 "OpenAI flags new concerning AI behavior"）
    "concern", "concerning", "worry", "worried", "worries", "alarm",
)

# 无主题的综合简报：标题里看不出讲什么，可能混进任何内容，一律不收。
ROUNDUP_PATTERNS = (
    "morning news brief", "news brief", "news roundup", "roundup",
    "daily briefing", "live updates", "what we know", "here's what to know",
    "things to know", "the week in", "in photos", "photos of the",
)

# 时政与外交。用户明确要求「避开时政，偏社会文化」。
# 刻意不收录 president / minister / government / policy / vote：这些词在
# 「大学校长」「教育政策」等正常语境里太常见，误杀面积过大。
POLITICAL_WORDS = (
    # 外交与安全
    "summit", "diplomacy", "diplomat", "spokesperson", "spokesman",
    "spokeswoman", "bilateral", "multilateral", "sanction", "tariff",
    "treaty", "ambassador", "delegation", "parliament", "congress",
    "senate", "senator", "election", "ballot", "referendum", "lawmaker",
    "legislator", "sovereignty", "geopolitic", "annexation", "propaganda",
    "crackdown", "suppression", "uyghur", "tibetan", "dissident",
    "white house", "kremlin", "pentagon", "state department",
    "foreign ministry", "united nations", "security council",
    "security dialogue", "press briefing", "five-year plan",
    # 中国官方口径（实测 CGTN/Ecns 头条高频出现）
    "xi jinping", "xi stresses", "xi urges", "xi calls", "xi says",
    "socialist", "long march", "red army", "premier", "state council",
    "scio", "brics", "apec", "sco", "taiwan", "mainland",
    # 国际冲突（实测漏过 "Israeli forces raze Palestinian olive trees"）
    "israel", "palestinian", "palestine", "gaza", "hamas", "hezbollah",
    "trump", "fema",
)

# 自动补的后缀。\b 边界是必须的："dead" 不能命中 deadline，"war" 不能命中
# software，"die" 不能命中 diesel —— 靠的都是 \b 加「后缀必须是完整白名单」。
# 刻意不收裸 "d"：那会让 "war" 命中 "ward"。
_SUFFIX = r"(?:s|es|ed|ing|ings|er|ers|ly|ism|ist|ists|ies)?"

_BLOCKED_RE = re.compile(
    r"\b(?:%s)%s\b" % (
        "|".join(re.escape(word) for word in NEGATIVE_WORDS + POLITICAL_WORDS),
        _SUFFIX,
    ),
    re.IGNORECASE,
)

_ROUNDUP_RE = re.compile(
    r"\b(?:%s)\b" % "|".join(re.escape(p) for p in ROUNDUP_PATTERNS),
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")     # Sixth Tone 的摘要里混着裸 URL
_WS_RE = re.compile(r"\s+")


def _localname(tag: str) -> str:
    """去掉 XML 命名空间前缀，让 RSS 2.0 与 Atom 用同一套取值逻辑。"""
    return tag.rsplit("}", 1)[-1]


def _strip_html(value: str) -> str:
    """剥标签 + 反转义 + 去掉裸 URL + 压空白。"""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _URL_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _child_text(item, names) -> str:
    """按名字顺序取第一个非空子元素文本。"""
    for child in item:
        if _localname(child.tag) in names:
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def _child_link(item) -> str:
    """取条目链接，兼容 RSS 的 <link>文本</link> 与 Atom 的 <link href=...>。"""
    for child in item:
        if _localname(child.tag) == "link":
            link = (child.get("href") or child.text or "").strip()
            if link:
                return link
    return ""


def _parse(raw: bytes, source: str) -> list:
    """解析 RSS 2.0 或 Atom，返回归一化后的素材列表。"""
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry")
    results = []
    for item in items[:PER_FEED_LIMIT]:
        title = _strip_html(_child_text(item, ("title",)))
        link = _child_link(item)
        if not title or not link:
            continue
        results.append({
            "title": title,
            "summary": _strip_html(
                _child_text(item, ("description", "summary", "content"))
            )[:SUMMARY_LIMIT],
            "link": link,
            "source": source,
            "published": _child_text(
                item, ("pubDate", "published", "updated", "date")),
        })
    return results


def fetch(timeout: int = 6) -> list:
    """顺序抓取全部源。单个源失败只损失它自己的条目；全失败则返回空列表。"""
    candidates = []
    for source, url in FEEDS:
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            candidates.extend(_parse(raw, source))
        except Exception as error:
            # 不回显 URL 与响应体，避免把内部信息写进日志。
            print("⚠️ 新闻源 %s 抓取失败（%s）" % (source, type(error).__name__),
                  file=sys.stderr)
    return candidates


def _is_blocked(title: str) -> bool:
    """标题命中负面事件词、时政词或综合简报模式则判为不合格。

    **只匹配标题，不匹配摘要。** 摘要经常长达 400+ 字符且是正文摘录，科学类
    摘要里的 "crashed"/"explosions"/"dead" 描述的是天文与生物现象而非坏消息，
    一起匹配会把 ScienceDaily 的优质科普大面积误杀（实测踩过：金星撞月、珊瑚礁
    复苏这类好内容都被过滤掉了）。新闻的负面性由标题承载。

    这仍是启发式，必然有误伤 —— 宁可错杀：兜底链保证不断更，词表可随时增删。
    """
    if not title:
        return True
    return bool(_BLOCKED_RE.search(title) or _ROUNDUP_RE.search(title))


def _recent_source_urls(n: int = 14) -> set:
    """最近 n 篇已用过的原文链接，用于避免短期内重复同一个话题。"""
    urls = set()
    files = sorted(glob.glob(str(ROOT / "articles" / "*.json")))[-n:]
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            url = (data.get("source") or {}).get("url")
            if isinstance(url, str) and url:
                urls.add(url)
        except Exception:
            pass
    return urls


def pick(date: str):
    """挑一条合格的新闻素材；没有合适的就返回 None，由调用方回退主题库。

    用日期做随机种子，保证同一天重试时选到同一条（与 gen_ai 的提示词只构建
    一次的行为一致），不同天则不同。
    """
    try:
        candidates = fetch()
        if not candidates:
            return None
        used = _recent_source_urls()
        usable = [
            item for item in candidates
            if item["link"] not in used and not _is_blocked(item["title"])
        ]
        if not usable:
            return None
        return random.Random(date).choice(usable)
    except Exception as error:
        print("⚠️ 新闻素材获取失败（%s），回退内置主题库" % type(error).__name__,
              file=sys.stderr)
        return None


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    everything = fetch()
    picked = pick(date)
    print("抓取到 %d 条，过滤后选中：" % len(everything))
    print(json.dumps(picked, ensure_ascii=False, indent=2))
