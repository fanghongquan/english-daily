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
from delivery_state import is_pushed, mark_pushed

ROOT = Path(__file__).parent


def _generate(root, source, date):
    subprocess.check_call([sys.executable, str(root / "get_article.py"),
                           "--source", source, "--date", date])


def run(a, *, root=ROOT, build_fn=build.build, push_fn=push_feishu.push,
        state_dir=None, generate_fn=None):
    root = Path(root)
    state_dir = Path(state_dir) if state_dir else root / "state"
    requested_date = a.date
    if not a.no_push and not a.force and is_pushed(state_dir, requested_date):
        print("今天已成功推送过，跳过本次（备用时段去重）")
        return

    if a.use_latest:
        files = sorted(glob.glob(str(root / "articles" / "*.json")))
        if not files:
            raise SystemExit("articles/ 下没有文章")
        art = Path(files[-1])
        a.date = art.stem
    else:
        art = root / "articles" / f"{a.date}.json"
        if a.force or not art.exists():
            generator = generate_fn or _generate
            generator(root, a.source, a.date)
            if not art.exists():
                raise RuntimeError(f"生成命令未创建文章：{art}")

    build_fn(str(art))
    if a.no_push:
        print("已跳过推送（--no-push）")
        return

    data = json.loads(art.read_text(encoding="utf-8"))
    base = os.environ.get("SITE_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit("请设置 SITE_BASE_URL")
    url = f"{base}/{a.date}.html"
    webhook = os.environ["FEISHU_WEBHOOK"]
    push_fn(webhook, os.environ.get("FEISHU_SECRET", ""),
            push_feishu.card(a.date, data["title"], data.get("title_zh", ""), url))
    mark_pushed(state_dir, requested_date, a.date, url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ai", "scrape"], default="ai")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--use-latest", action="store_true",
                    help="不生成新文章，直接用 articles/ 里最新一篇（内容引擎没接好时用）")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-audio", action="store_true", help="跳过云端语音预生成")
    ap.add_argument("--force", action="store_true",
                    help="强制重新生成今天的文章并推送（即使已存在），用于手动重做当天内容")
    a = ap.parse_args()

    run(a)


if __name__ == "__main__":
    main()
