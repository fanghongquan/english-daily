#!/usr/bin/env python3
"""通过飞书「群自定义机器人」webhook 推送一张交互卡片，带标题 + 当日阅读链接。

环境变量：
    FEISHU_WEBHOOK   群自定义机器人的 webhook 地址（必填）
    FEISHU_SECRET    机器人「签名校验」密钥（如果你在飞书里开了加签，则必填）

用法：
    python push_feishu.py --date 2026-06-13 \
        --title "Why We Procrastinate and How to Beat It" \
        --title-zh "我们为什么拖延，又该如何战胜它" \
        --url "https://<你的用户名>.github.io/english-daily/2026-06-13.html"
"""
import os, json, time, hmac, base64, hashlib, argparse, urllib.request
import envload; envload.load()      # 自动读取 secret.env


def sign(secret: str, ts: str) -> str:
    s = f"{ts}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(s, digestmod=hashlib.sha256).digest()).decode()


def card(date, title, title_zh, url):
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": f"📖 今日英语 · {date}"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
             "content": f"**{title}**\n{title_zh}"}},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "约 1000 词 · CET-4 难度 · 段段对照翻译 · 选词/选句可听美式发音"}},
            {"tag": "hr"},
            {"tag": "action", "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "▶ 开始今天的阅读"},
                "type": "primary",
                "url": url,
            }]},
            {"tag": "note", "elements": [{"tag": "plain_text",
             "content": "建议用 Safari / Chrome 打开，发音效果最佳"}]},
        ],
    }


def push(webhook, secret, payload):
    body = {"msg_type": "interactive", "card": payload}
    if secret:
        ts = str(int(time.time()))
        body["timestamp"] = ts
        body["sign"] = sign(secret, ts)
    req = urllib.request.Request(
        webhook, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode()
    print("飞书返回:", raw)
    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("飞书返回的不是合法 JSON") from exc
    code = response.get("code", response.get("StatusCode"))
    if code != 0:
        message = response.get("msg", response.get("StatusMessage", "unknown error"))
        raise RuntimeError(f"飞书返回错误码 {code}: {message}")
    return response


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--title-zh", default="")
    ap.add_argument("--url", required=True)
    a = ap.parse_args()

    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        raise SystemExit("请先设置环境变量 FEISHU_WEBHOOK")
    push(webhook, os.environ.get("FEISHU_SECRET", ""),
         card(a.date, a.title, a.title_zh, a.url))
