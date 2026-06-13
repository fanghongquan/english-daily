#!/usr/bin/env python3
"""用腾讯云语音合成(在线接口 TextToVoice)为当天文章预生成自然发音 mp3。

只用「在线/通用语音合成」接口（被 800 万字符免费额度覆盖）；长段落会自动
按句子切成 ≤120 字符的小块、再把各块 mp3 直接拼接，规避「长文本异步合成」
那个单独计费的产品。

会为：整篇全文、每个自然段、每个重点词 各生成一个 mp3，存到
site/audio/<日期>/，并把路径写回文章 JSON 的 "audio" 字段，供网页优先播放
（任意选词仍回退浏览器实时合成）。

依赖：pip install tencentcloud-sdk-python
环境变量：
    TENCENT_SECRET_ID    腾讯云 SecretId
    TENCENT_SECRET_KEY   腾讯云 SecretKey（保密那半，别外泄）
    TTS_VOICE            可选，音色 VoiceType（默认 101051 = 精品英文女声 WeRose）
"""
import os, sys, re, json, glob, base64, hashlib
from pathlib import Path
import envload; envload.load()      # 自动读取 secret.env

ROOT = Path(__file__).parent

# 音色 VoiceType（完整列表见腾讯云「语音合成-音色列表」文档）：
#   英文·精品(走 800 万免费额度)：101050 WeJack(男)  101051 WeRose(女)
#   英文·基础：1050 / 1051
#   想最自然可换「大模型音色」(走另外 10 万免费额度)
VOICE = int(os.environ.get("TTS_VOICE", "101051"))
CHUNK = 120          # 单次在线合成的安全字符上限


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def chunks(text):
    """按句子切分，累积到 ≤CHUNK 字符；超长单句再按逗号/空格兜底切。"""
    parts = re.split(r"(?<=[.!?;:])\s+", text)
    buf, out = "", []
    for s in parts:
        while len(s) > CHUNK:                      # 兜底：超长句再切
            cut = s.rfind(" ", 0, CHUNK)
            cut = cut if cut > 0 else CHUNK
            out.append(s[:cut].strip()); s = s[cut:].strip()
        if len(buf) + len(s) + 1 <= CHUNK:
            buf = (buf + " " + s).strip()
        else:
            if buf: out.append(buf)
            buf = s
    if buf: out.append(buf)
    return out


def client():
    from tencentcloud.common import credential
    from tencentcloud.tts.v20190823 import tts_client
    sid = os.environ.get("TENCENT_SECRET_ID")
    skey = os.environ.get("TENCENT_SECRET_KEY")
    if not sid or not skey:
        sys.exit("请先设置环境变量 TENCENT_SECRET_ID 和 TENCENT_SECRET_KEY")
    return tts_client.TtsClient(credential.Credential(sid, skey), "ap-guangzhou")


def synth_chunk(cli, text):
    from tencentcloud.tts.v20190823 import models
    req = models.TextToVoiceRequest()
    sess = hashlib.md5(text.encode()).hexdigest()[:16]
    req.from_json_string(json.dumps({
        "Text": text, "SessionId": sess, "VoiceType": VOICE,
        "Codec": "mp3", "SampleRate": 16000, "PrimaryLanguage": 2}))  # 2=英文
    return base64.b64decode(cli.TextToVoice(req).Audio)


def synth(cli, text):
    """长文本切块合成后拼接 mp3 字节。"""
    return b"".join(synth_chunk(cli, c) for c in chunks(text.strip()))


def main(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    date = data["date"]
    outdir = ROOT / "docs" / "audio" / date
    outdir.mkdir(parents=True, exist_ok=True)
    rel = f"audio/{date}"
    cli = client()
    audio = {"full": None, "paras": [], "vocab": {}}

    full_text = " ".join(plain(p["en"]) for p in data["paragraphs"])
    (outdir / "full.mp3").write_bytes(synth(cli, full_text))
    audio["full"] = f"{rel}/full.mp3"
    print("✓ full")

    for i, p in enumerate(data["paragraphs"]):
        (outdir / f"p{i}.mp3").write_bytes(synth(cli, plain(p["en"])))
        audio["paras"].append(f"{rel}/p{i}.mp3")
        print(f"✓ 段 {i+1}/{len(data['paragraphs'])}")

    for v in data.get("vocab", []):
        w = v["w"]
        fn = re.sub(r"[^a-zA-Z0-9_-]", "_", w)
        (outdir / f"v_{fn}.mp3").write_bytes(synth(cli, w))
        audio["vocab"][w] = f"{rel}/v_{fn}.mp3"
    print(f"✓ 重点词 ×{len(audio['vocab'])}")

    data["audio"] = audio
    Path(json_path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print("已写回音频路径到", json_path)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else \
        sorted(glob.glob(str(ROOT / "articles" / "*.json")))[-1]
    main(src)
