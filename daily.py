#!/usr/bin/env python3
"""每日一键流程：生成文章 → 渲染网页 → 推送飞书卡片。

环境变量：
    SITE_BASE_URL    页面根地址，如 https://<用户名>.github.io/english-daily
    FEISHU_WEBHOOK   飞书群机器人 webhook
    FEISHU_SECRET    加签密钥（如启用）
    以及 get_article.py 所需的 ANTHROPIC_API_KEY / OPENAI_API_KEY（--source ai 时）

用法：
    python daily.py                  # 默认 ai 生成今天的文章并推送
    python daily.py --source ai
    python daily.py --use-latest     # 不生成，直接推送 articles/ 里最新一篇（先跑通流程用）
    python daily.py --no-push        # 只生成+构建，不推送（本地调试）
"""
import os, json, datetime, argparse, subprocess, sys, glob
from pathlib import Path
import envload; envload.load()      # 自动读取 secret.env
import build, push_feishu

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ai", "scrape"], default="ai")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--use-latest", action="store_true",
                    help="不生成新文章，直接用 articles/ 里最新一篇（内容引擎没接好时用）")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-audio", action="store_true", help="跳过云端语音预生成")
    a = ap.parse_args()

    if a.use_latest:
        files = sorted(glob.glob(str(ROOT / "articles" / "*.json")))
        if not files:
            raise SystemExit("articles/ 下没有文章")
        art = Path(files[-1])
        a.date = art.stem                       # 用该文章自身的日期
    else:
        art = ROOT / "articles" / f"{a.date}.json"
        if not art.exists():
            subprocess.check_call([sys.executable, str(ROOT / "get_article.py"),
                                   "--source", a.source, "--date", a.date])

    # 如配置了腾讯云密钥，则预生成自然语音 mp3（否则网页用浏览器实时合成）
    if not a.no_audio and os.environ.get("TENCENT_SECRET_ID") \
            and os.environ.get("TENCENT_SECRET_KEY"):
        try:
            subprocess.check_call([sys.executable, str(ROOT / "gen_audio.py"), str(art)])
        except Exception as e:
            print("⚠️ 生成语音失败，跳过（网页将回退浏览器合成）:", e)

    build.build(str(art))

    if a.no_push:
        print("已跳过推送（--no-push）")
        return

    data = json.loads(art.read_text(encoding="utf-8"))
    base = os.environ.get("SITE_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit("请设置 SITE_BASE_URL")
    url = f"{base}/{a.date}.html"

    webhook = os.environ["FEISHU_WEBHOOK"]
    push_feishu.push(webhook, os.environ.get("FEISHU_SECRET", ""),
                     push_feishu.card(a.date, data["title"],
                                      data.get("title_zh", ""), url))


if __name__ == "__main__":
    main()
