#!/usr/bin/env python3
"""把某一天的文章 JSON 渲染成自包含的 HTML 页面，并更新 index.html 跳转到最新一篇。

用法：
    python build.py articles/2026-06-13.json
    python build.py                      # 不带参数则取 articles/ 下日期最新的一篇
"""
import json, sys, glob, os, html
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "docs"     # GitHub Pages「从分支部署」支持 /docs
TEMPLATE = ROOT / "template.html"


def pick_latest():
    files = sorted(glob.glob(str(ROOT / "articles" / "*.json")))
    if not files:
        sys.exit("articles/ 下没有任何文章 JSON")
    return files[-1]


def build(json_path: str) -> str:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    tts_api = os.environ.get("TTS_API_URL", "")     # 腾讯云函数地址(GitHub 变量)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    page = (tpl
            .replace("__ARTICLE_DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__TITLE__", html.escape(data.get("title", "每日英语")))
            .replace("__TTS_API__", tts_api))
    SITE.mkdir(exist_ok=True)
    out = SITE / f"{data['date']}.html"
    out.write_text(page, encoding="utf-8")

    # index.html 跳转到最新一篇
    (SITE / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0; url=./{data["date"]}.html">'
        f'<a href="./{data["date"]}.html">今日英语阅读 →</a>',
        encoding="utf-8")
    print("已生成", out)
    return str(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else pick_latest()
    build(src)
