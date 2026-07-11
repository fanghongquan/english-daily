#!/usr/bin/env python3
"""把某一天的文章 JSON 渲染成自包含的 HTML 页面，并更新 index.html 跳转到最新一篇。

用法：
    python build.py articles/2026-06-13.json
    python build.py                      # 不带参数则取 articles/ 下日期最新的一篇
"""
import json, sys, glob, os, html
from pathlib import Path
from article_validation import prepare_article

ROOT = Path(__file__).parent
SITE = ROOT / "docs"     # GitHub Pages「从分支部署」支持 /docs
TEMPLATE = ROOT / "template.html"


def _json_for_script(value):
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))

# 历史目录页（index.html）——自包含、支持夜间模式，风格与阅读页一致
ARCHIVE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<title>每日英语 · 历史目录</title>
<script>
(function(){try{var t=localStorage.getItem('theme');
  if(t!=='light'&&t!=='dark') t=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
</script>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--ink:#1f2329;--sub:#646a73;--line:#e5e6eb;
    --accent:#3370ff;--kw:#1456f0;--zh:#8a5a00;--hover:#f0f4ff;}
  html[data-theme="dark"]{--bg:#15171a;--card:#22262b;--ink:#e6e8eb;--sub:#9aa0a6;
    --line:#343a42;--accent:#6b97ff;--kw:#86a9ff;--zh:#e3b877;--hover:#262d39;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Segoe UI,Roboto,sans-serif;
    line-height:1.5;-webkit-font-smoothing:antialiased}
  .wrap{max-width:720px;margin:0 auto;padding:20px 16px 60px}
  header{display:flex;align-items:center;justify-content:space-between;gap:10px;
    padding:4px 2px 14px;border-bottom:1px solid var(--line);margin-bottom:6px}
  h1{font-size:22px;margin:0}
  h1 .sub{font-size:13px;color:var(--sub);font-weight:400;margin-left:8px}
  .tg{border:1px solid var(--line);background:var(--card);color:var(--ink);
    border-radius:20px;padding:6px 13px;font-size:13px;cursor:pointer}
  .list{margin-top:6px}
  a.row{display:flex;align-items:baseline;gap:12px;text-decoration:none;color:inherit;
    padding:13px 12px;border-bottom:1px solid var(--line);border-radius:8px}
  a.row:hover{background:var(--hover)}
  .row .d{font-size:12.5px;color:var(--sub);font-variant-numeric:tabular-nums;min-width:86px;flex-shrink:0}
  .row .t{display:flex;flex-direction:column;gap:2px}
  .row .en{font-size:15.5px;font-weight:600;color:var(--kw)}
  .row .zh{font-size:13px;color:var(--sub)}
  .row.today .d::after{content:"今天";display:inline-block;margin-left:6px;font-size:11px;
    color:#fff;background:var(--accent);border-radius:6px;padding:1px 6px}
  footer{text-align:center;color:var(--sub);font-size:12px;margin-top:26px}
  @media(max-width:480px){.row .d{min-width:0;flex-basis:100%}.row{flex-wrap:wrap;gap:4px 12px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📚 每日英语 · 历史目录<span class="sub">共 __COUNT__ 篇</span></h1>
    <button class="tg" id="tg" onclick="(function(){var d=document.documentElement.getAttribute('data-theme')==='dark';var n=d?'light':'dark';document.documentElement.setAttribute('data-theme',n);try{localStorage.setItem('theme',n);}catch(e){}document.getElementById('tg').textContent=n==='dark'?'☀️ 日间':'🌙 夜间';})()">🌙 夜间</button>
  </header>
  <div class="list">
__ROWS__
  </div>
  <footer>每天 12:13 自动更新 · 选词发音 / 划词翻译 / 一键存墨墨</footer>
</div>
<script>
  (function(){var d=document.documentElement.getAttribute('data-theme')==='dark';
    document.getElementById('tg').textContent=d?'☀️ 日间':'🌙 夜间';})();
</script>
</body>
</html>"""


def _write_archive():
    """扫描 articles/ 下全部文章，生成历史目录 index.html（按日期倒序）。"""
    files = sorted(glob.glob(str(ROOT / "articles" / "*.json")), reverse=True)
    rows = []
    today = ""
    try:
        import datetime
        today = datetime.date.today().isoformat()
    except Exception:
        pass
    for f in files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        date = d.get("date") or Path(f).stem
        title = html.escape(d.get("title", "") or "")
        title_zh = html.escape(d.get("title_zh", "") or "")
        cls = "row today" if date == today else "row"
        rows.append(
            f'    <a class="{cls}" href="./{date}.html">'
            f'<span class="d">{date}</span>'
            f'<span class="t"><span class="en">{title}</span>'
            f'<span class="zh">{title_zh}</span></span></a>')
    page = (ARCHIVE_TMPL
            .replace("__ROWS__", "\n".join(rows) or '    <p style="color:var(--sub)">还没有文章</p>')
            .replace("__COUNT__", str(len(rows))))
    (SITE / "index.html").write_text(page, encoding="utf-8")


def pick_latest():
    files = sorted(glob.glob(str(ROOT / "articles" / "*.json")))
    if not files:
        sys.exit("articles/ 下没有任何文章 JSON")
    return files[-1]


def build(json_path: str) -> str:
    data = prepare_article(json.loads(Path(json_path).read_text(encoding="utf-8")))
    tts_api = os.environ.get("TTS_API_URL", "")     # 腾讯云函数地址(GitHub 变量)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    page = (tpl
            .replace("__ARTICLE_DATA__", _json_for_script(data))
            .replace("__TITLE__", html.escape(data.get("title", "每日英语")))
            .replace("__TTS_API__", _json_for_script(tts_api)))
    SITE.mkdir(exist_ok=True)
    out = SITE / f"{data['date']}.html"
    out.write_text(page, encoding="utf-8")

    # index.html 改为「历史目录」页（列出全部文章）
    _write_archive()
    print("已生成", out)
    return str(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else pick_latest()
    build(src)
