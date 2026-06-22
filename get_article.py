#!/usr/bin/env python3
"""生成「当日文章」JSON（schema 见 articles/2026-06-13.json）。

支持两种来源：
  --source ai      用大模型生成一篇 CET-4 难度文章（推荐，无版权风险）
  --source scrape  从外刊/真题站点抓取（占位实现，需你自行接入并注意版权，见下方说明）

输出文件：articles/<日期>.json

防雷同设计：
  1. 内置一个多领域题材库 TOPICS，按日期轮换，保证连续几十天不会撞主题；
  2. 把最近若干天已用过的标题喂给模型，要求它另选完全不同的领域；
  3. 调高 temperature，提升用词与结构的多样性。
"""
import os, json, datetime, argparse, re, glob, random
from pathlib import Path
import envload; envload.load()      # 自动读取 secret.env

ROOT = Path(__file__).parent
SCHEMA_HINT = (ROOT / "articles" / "2026-06-13.json")

# ---- 多领域题材库：每天轮换一个，跨科普/文化/历史/自然/科技/社会/人物 ----------
TOPICS = [
    "深海生物的奇特世界", "睡眠对大脑的重要性", "蜜蜂如何为植物授粉",
    "候鸟为什么要长途迁徙", "火山是如何形成的", "人类记忆的运作原理",
    "可再生能源的发展", "太空垃圾问题", "雷暴和闪电背后的科学",
    "为什么天空是蓝色的", "咖啡是如何传遍世界的", "世界各地的茶文化",
    "节日烟花的由来", "街头美食的魅力", "传统手工艺的传承",
    "电影是怎样诞生的", "丝绸之路上的贸易故事", "古代奥林匹克运动会",
    "印刷术如何改变世界", "长城的历史与建造", "塑料污染与海洋保护",
    "城市里的绿色空间", "珊瑚礁为什么重要", "国家公园的意义",
    "垃圾分类与回收", "健康饮食的小常识", "运动如何改善心情",
    "做志愿者的收获", "年轻人理财入门", "公共交通的好处",
    "养宠物给人的陪伴", "智能手机如何改变生活", "在线学习的兴起",
    "电动汽车的时代", "机器人走进日常生活", "虚拟现实技术",
    "改变世界的发明家", "运动员背后的坚持", "好奇心驱动的科学家",
    "城市生活与乡村生活", "跨文化交流的乐趣", "学习一门外语的好处",
    "阅读为什么让人快乐", "音乐对情绪的影响", "旅行如何开阔眼界",
    "友谊在生活中的意义", "时间都去哪儿了：高效安排一天",
]


def _recent_titles(n: int = 8) -> list:
    """读取最近 n 篇已生成文章的标题，用于提示模型避免重复。"""
    files = sorted(glob.glob(str(ROOT / "articles" / "*.json")))[-n:]
    titles = []
    for f in files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            t = d.get("title") or ""
            tz = d.get("title_zh") or ""
            if t or tz:
                titles.append(f"{t}（{tz}）".strip("（）"))
        except Exception:
            pass
    return titles


def _pick_topic(date: str) -> str:
    """按日期轮换题材，保证每天不同；越界后再从头循环。"""
    try:
        ordinal = datetime.date.fromisoformat(date).toordinal()
    except Exception:
        ordinal = datetime.date.today().toordinal()
    return TOPICS[ordinal % len(TOPICS)]


SYS = "你是一名资深大学英语四级(CET-4)命题老师和翻译。"

PROMPT_TMPL = """请生成一篇适合中国大学英语四级(CET-4)水平的英语阅读文章，并按 JSON 返回。

【本篇主题（必须严格围绕它来写）】：%(topic)s

【务必避免雷同】最近已经推送过下面这些文章，请另选完全不同的角度与用词，不要再写“习惯/自我提升/原子习惯”这类老套主题，也不要与下列任何一篇在主题、例子、结构上相似：
%(avoid)s

要求：
1. 文章总长约 1000 词，内容贴近生活/科普/文化，积极正向、信息丰富、有具体事例和数据；
2. 拆成 7-9 个自然段；
3. 每段挑 2-3 个四级核心词作为重点词，用 <span class="kw" data-ipa="美式音标" data-def="中文释义">单词</span> 包裹（音标用美式 IPA）；
4. 每段配一段地道的中文翻译；
5. 末尾汇总 15-20 个重点词汇表；
6. 标题要具体、有新意，能直接看出本篇主题，不要用泛泛的“The Power of …”套路。
严格只输出如下结构的 JSON（不要多余文字）：
{
 "date":"%(date)s","level":"CET-4","title":"...", "title_zh":"...",
 "intro_zh":"本文约 1000 词……",
 "paragraphs":[{"en":"含 kw 标签的英文 HTML","zh":"中文翻译"}, ...],
 "vocab":[{"w":"单词","ipa":"/.../","def":"词性+中文"}, ...]
}"""


def _build_prompt(date: str) -> str:
    topic = _pick_topic(date)
    recent = _recent_titles()
    avoid = "\n".join(f"- {t}" for t in recent) if recent else "（暂无历史记录）"
    return PROMPT_TMPL % {"date": date, "topic": topic, "avoid": avoid}


def gen_ai(date: str) -> dict:
    """用 Anthropic 或 OpenAI 兼容接口生成。按你拥有的 key 自动选择。"""
    prompt = _build_prompt(date)
    # --- Anthropic ---
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=8000, system=SYS, temperature=1.0,
            messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
    # --- OpenAI / 兼容（DeepSeek、通义、Kimi 等都可用同一 SDK）---
    elif os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI  # pip install openai
        client = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},   # DeepSeek/OpenAI JSON 模式更稳
            temperature=1.1,                            # 提高多样性，减少千篇一律
            messages=[{"role": "system", "content": SYS},
                      {"role": "user", "content": prompt}])
        text = r.choices[0].message.content
    else:
        raise SystemExit("未检测到 ANTHROPIC_API_KEY 或 OPENAI_API_KEY")

    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0))
    data["date"] = date
    return data


def gen_scrape(date: str) -> dict:
    """占位：从外刊/真题站点抓取。

    ⚠️ 版权提醒：四级真题、The Economist、China Daily 等外刊文章多受版权保护，
    抓取后整篇转发推送可能侵权。合规做法建议二选一：
      (a) 仅抓「公共领域 / 知识共享」来源（如 VOA Learning English、维基百科节选、
          古登堡计划等），它们允许再使用；
      (b) 抓来的文章只作为「素材」喂给大模型，让模型改写+简化到四级难度后再用
          （改写后的内容版权属于你），同时附上原文出处链接。
    """
    raise NotImplementedError(
        "scrape 来源需你自行接入合规数据源，见本函数 docstring 的版权提醒。"
        "默认建议先用 --source ai。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ai", "scrape"], default="ai")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    data = gen_ai(a.date) if a.source == "ai" else gen_scrape(a.date)
    out = ROOT / "articles" / f"{a.date}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已生成", out, "｜主题：", _pick_topic(a.date))
