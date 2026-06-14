#!/usr/bin/env python3
"""生成「当日文章」JSON（schema 见 articles/2026-06-13.json）。

支持两种来源：
  --source ai      用大模型生成一篇 CET-4 难度文章（推荐，无版权风险）
  --source scrape  从外刊/真题站点抓取（占位实现，需你自行接入并注意版权，见下方说明）

输出文件：articles/<日期>.json
"""
import os, json, datetime, argparse, re
from pathlib import Path
import envload; envload.load()      # 自动读取 secret.env

ROOT = Path(__file__).parent
SCHEMA_HINT = (ROOT / "articles" / "2026-06-13.json")

# ---- 大模型生成的 system / user 提示词 ----------------------------------
SYS = "你是一名资深大学英语四级(CET-4)命题老师和翻译。"

PROMPT = """请生成一篇适合中国大学英语四级(CET-4)水平的英语阅读文章，并按 JSON 返回。
要求：
1. 文章总长约 1000 词，话题贴近生活/科普/文化，积极正向；
2. 拆成 7-9 个自然段；
3. 每段挑 2-3 个四级核心词作为重点词，用 <span class="kw" data-ipa="美式音标" data-def="中文释义">单词</span> 包裹（音标用美式 IPA）；
4. 每段配一段地道的中文翻译；
5. 末尾汇总 15-20 个重点词汇表。
严格只输出如下结构的 JSON（不要多余文字）：
{
 "date":"%(date)s","level":"CET-4","title":"...", "title_zh":"...",
 "intro_zh":"本文约 1000 词……",
 "paragraphs":[{"en":"含 kw 标签的英文 HTML","zh":"中文翻译"}, ...],
 "vocab":[{"w":"单词","ipa":"/.../","def":"词性+中文"}, ...]
}"""


def gen_ai(date: str) -> dict:
    """用 Anthropic 或 OpenAI 兼容接口生成。按你拥有的 key 自动选择。"""
    prompt = PROMPT % {"date": date}
    # --- Anthropic ---
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=8000, system=SYS,
            messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
    # --- OpenAI / 兼容（DeepSeek、通义、Kimi 等都可用同一 SDK）---
    elif os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI  # pip install openai
        client = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},   # DeepSeek/OpenAI JSON 模式更稳
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
    下面给出 VOA Learning English 的抓取骨架，你按需补全解析逻辑。
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
    print("已生成", out)
