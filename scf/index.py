# -*- coding: utf-8 -*-
"""腾讯云 SCF 函数：①语音合成(发音) ②遗忘库多设备同步(读写 COS)。

纯标准库实现，无需安装依赖，可直接粘进 SCF 内联编辑器。
前端用同一个「函数 URL」POST JSON，按 op 路由：
  {"op":"tts","text":"...","voice":101051}      -> {"audio":"<base64 mp3>"}
  {"op":"get","key":"<同步码>"}                 -> {"lib":[...]}
  {"op":"put","key":"<同步码>","lib":[...]}     -> {"ok":true}
  不带 op 默认当作 tts。

凭证(按优先级)：
  1) SCF 运行角色自动注入的临时密钥(推荐，给函数绑定带 TTS+COS 权限的角色)
     TENCENTCLOUD_SECRETID / TENCENTCLOUD_SECRETKEY / TENCENTCLOUD_SESSIONTOKEN
  2) 环境变量 TENCENT_SECRET_ID / TENCENT_SECRET_KEY
环境变量：
  TTS_VOICE     默认音色，默认 101051
  COS_BUCKET    存储桶全名(含 APPID)，如 english-daily-1300942703   ← 同步功能必填
  COS_REGION    存储桶地域，默认 ap-guangzhou
  APP_ACCESS_KEY  浏览器请求签名用的高强度个人访问码(必填)
  ALLOW_ORIGIN    允许的精确网页来源，如 https://fanghongquan.github.io
  RATE_BURST      单实例突发请求数，默认 20
  RATE_PER_MINUTE 单实例每分钟补充令牌数，默认 30
"""
import os, json, time, hmac, hashlib, base64, re, urllib.request, urllib.parse, urllib.error

TTS_HOST = "tts.tencentcloudapi.com"
DEFAULT_VOICE = int(os.environ.get("TTS_VOICE", "101051"))
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "*")
CHUNK = 120
MAX_BODY = 16 * 1024
RATE_BURST = int(os.environ.get("RATE_BURST", "20"))
RATE_PER_MINUTE = float(os.environ.get("RATE_PER_MINUTE", "30"))
_RATE = {}


def _creds():
    sid = os.environ.get("TENCENTCLOUD_SECRETID") or os.environ.get("TENCENT_SECRET_ID")
    skey = os.environ.get("TENCENTCLOUD_SECRETKEY") or os.environ.get("TENCENT_SECRET_KEY")
    token = os.environ.get("TENCENTCLOUD_SESSIONTOKEN", "")
    return sid, skey, token


# ---------------- 语音合成 (TC3-HMAC-SHA256) ----------------
def _tc3_headers(sid, skey, token, payload):
    ts = int(time.time()); date = time.strftime("%Y-%m-%d", time.gmtime(ts))
    ct = "application/json; charset=utf-8"
    canonical = "\n".join(["POST", "/", "",
        "content-type:%s\nhost:%s\n" % (ct, TTS_HOST), "content-type;host",
        hashlib.sha256(payload.encode()).hexdigest()])
    scope = "%s/tts/tc3_request" % date
    s2s = "\n".join(["TC3-HMAC-SHA256", str(ts), scope,
        hashlib.sha256(canonical.encode()).hexdigest()])
    def hm(k, m): return hmac.new(k, m.encode(), hashlib.sha256).digest()
    sk = hm(hm(hm(("TC3" + skey).encode(), date), "tts"), "tc3_request")
    sig = hmac.new(sk, s2s.encode(), hashlib.sha256).hexdigest()
    h = {"Authorization": "TC3-HMAC-SHA256 Credential=%s/%s, SignedHeaders=content-type;host, Signature=%s" % (sid, scope, sig),
         "Content-Type": ct, "Host": TTS_HOST, "X-TC-Action": "TextToVoice",
         "X-TC-Timestamp": str(ts), "X-TC-Version": "2019-08-23", "X-TC-Region": "ap-guangzhou"}
    if token: h["X-TC-Token"] = token
    return h


def _synth_one(sid, skey, token, text, voice):
    sess = hashlib.md5(text.encode()).hexdigest()[:16]
    payload = json.dumps({"Text": text, "SessionId": sess, "VoiceType": voice,
        "Codec": "mp3", "SampleRate": 16000, "PrimaryLanguage": 2}, ensure_ascii=False)
    req = urllib.request.Request("https://" + TTS_HOST + "/", data=payload.encode(),
        headers=_tc3_headers(sid, skey, token, payload), method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.loads(r.read().decode())["Response"]
    if "Error" in resp: raise RuntimeError(resp["Error"].get("Message", "tts error"))
    return base64.b64decode(resp["Audio"])


def _chunks(text):
    parts = re.split(r"(?<=[.!?;:])\s+", text.strip()); buf, out = "", []
    for s in parts:
        while len(s) > CHUNK:
            c = s.rfind(" ", 0, CHUNK); c = c if c > 0 else CHUNK
            out.append(s[:c].strip()); s = s[c:].strip()
        if len(buf) + len(s) + 1 <= CHUNK: buf = (buf + " " + s).strip()
        else:
            if buf: out.append(buf)
            buf = s
    if buf: out.append(buf)
    return out or [text.strip()]


def do_tts(sid, skey, token, text, voice):
    audio = b"".join(_synth_one(sid, skey, token, c, voice) for c in _chunks(text))
    return {"audio": base64.b64encode(audio).decode("ascii")}


# ---------------- 墨墨背单词云词本 ----------------
MAIMEMO_BASE = "https://open.maimemo.com/open/api/v1"
MAIMEMO_TITLE = os.environ.get("MAIMEMO_TITLE", "每日英语·生词本")


def _mm_req(method, path, token, body=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(MAIMEMO_BASE + path, data=data,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def _mm_find(token):
    for offset in range(0, 100, 10):
        result = _mm_req("GET", "/notepads?limit=10&offset=%d" % offset, token)
        items = (result.get("data") or {}).get("notepads", [])
        for item in items:
            if item.get("title") == MAIMEMO_TITLE:
                return item.get("id")
        if len(items) < 10:
            break
    return None


def do_maimemo(token, word):
    notebook_id = _mm_find(token)
    if notebook_id:
        result = _mm_req("GET", "/notepads/" + notebook_id, token)
        content = ((result.get("data") or {}).get("notepad") or {}).get("content", "")
    else:
        content = "#%s#\n" % MAIMEMO_TITLE
    words = [line.strip() for line in content.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    if word.lower() in {item.lower() for item in words}:
        return {"ok": True, "dup": True, "total": len(words)}
    content = content.rstrip("\n") + "\n" + word + "\n"
    body = {"notepad": {"status": "UNPUBLISHED", "content": content,
            "title": MAIMEMO_TITLE, "brief": "来自每日英语", "tags": ["english"]}}
    path = "/notepads/" + notebook_id if notebook_id else "/notepads"
    _mm_req("POST", path, token, body)
    return {"ok": True, "total": len(words) + 1}


# ---------------- COS 读写 (q-signature, 用于同步) ----------------
def _cos_auth(method, path, sid, skey):
    now = int(time.time()); kt = "%d;%d" % (now, now + 600)
    signkey = hmac.new(skey.encode(), kt.encode(), hashlib.sha1).hexdigest()
    httpstr = "%s\n%s\n\n%s\n" % (method.lower(), path, "")  # 无 query、不签 header
    s2s = "sha1\n%s\n%s\n" % (kt, hashlib.sha1(httpstr.encode()).hexdigest())
    sig = hmac.new(signkey.encode(), s2s.encode(), hashlib.sha1).hexdigest()
    return ("q-sign-algorithm=sha1&q-ak=%s&q-sign-time=%s&q-key-time=%s"
            "&q-header-list=&q-url-param-list=&q-signature=%s") % (sid, kt, kt, sig)


def _cos_req(method, objkey, sid, skey, token, body=None):
    bucket = os.environ.get("COS_BUCKET"); region = os.environ.get("COS_REGION", "ap-guangzhou")
    if not bucket: raise RuntimeError("COS_BUCKET not set")
    host = "%s.cos.%s.myqcloud.com" % (bucket, region)
    path = "/" + objkey
    h = {"Authorization": _cos_auth(method, path, sid, skey), "Host": host}
    if token: h["x-cos-security-token"] = token
    if body is not None: h["Content-Type"] = "application/json"
    req = urllib.request.Request("https://" + host + path, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _objkey(key):
    return "forgetlib/" + hashlib.sha256(("fl:" + key).encode()).hexdigest() + ".json"


def do_get(sid, skey, token, key):
    try:
        data = _cos_req("GET", _objkey(key), sid, skey, token)
        return {"lib": json.loads(data.decode())}
    except urllib.error.HTTPError as e:
        if e.code == 404: return {"lib": []}      # 还没存过
        raise


def do_put(sid, skey, token, key, lib):
    body = json.dumps(lib, ensure_ascii=False).encode()
    _cos_req("PUT", _objkey(key), sid, skey, token, body)
    return {"ok": True}


# ---------------- 应用鉴权、来源限制与单实例限流 ----------------
def _headers(event):
    return {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}


def _expected_signature(access_key, timestamp, nonce, raw_body):
    digest = hashlib.sha256(raw_body.encode()).hexdigest()
    canonical = "%s\n%s\n%s" % (timestamp, nonce, digest)
    return hmac.new(access_key.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def _authorize(event, raw_body, now=None):
    headers = _headers(event)
    origin = headers.get("origin", "")
    if not ALLOW_ORIGIN or ALLOW_ORIGIN == "*" or origin != ALLOW_ORIGIN:
        return 403, "origin not allowed"
    access_key = os.environ.get("APP_ACCESS_KEY", "")
    if len(access_key) < 24:
        return 500, "server authentication is not configured"
    timestamp = headers.get("x-app-timestamp", "")
    nonce = headers.get("x-app-nonce", "")
    signature = headers.get("x-app-signature", "")
    try:
        request_time = int(timestamp)
    except ValueError:
        return 401, "invalid signature"
    now = int(time.time() if now is None else now)
    if abs(now - request_time) > 300:
        return 401, "expired signature"
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce):
        return 401, "invalid signature"
    expected = _expected_signature(access_key, timestamp, nonce, raw_body)
    if not re.fullmatch(r"[0-9a-f]{64}", signature) or not hmac.compare_digest(expected, signature):
        return 401, "invalid signature"
    return None


def _source_ip(event):
    context = event.get("requestContext") or {}
    return (context.get("sourceIp") or (context.get("http") or {}).get("sourceIp")
            or "unknown")


def _rate_allowed(key, now=None):
    now = time.time() if now is None else now
    tokens, updated = _RATE.get(key, (float(RATE_BURST), now))
    tokens = min(float(RATE_BURST), tokens + max(0, now - updated) * RATE_PER_MINUTE / 60.0)
    if tokens < 1:
        _RATE[key] = (tokens, now)
        return False
    _RATE[key] = (tokens - 1, now)
    return True


# ---------------- 入口 ----------------
def _resp(code, body, is_json=True, origin=None):
    return {"isBase64Encoded": False, "statusCode": code,
        "headers": {"Content-Type": "application/json; charset=utf-8" if is_json else "text/plain",
            "Access-Control-Allow-Origin": origin or ALLOW_ORIGIN,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "content-type,x-app-timestamp,x-app-nonce,x-app-signature",
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        "body": json.dumps(body, ensure_ascii=False) if is_json else body}


def main_handler(event, context):
    headers = _headers(event)
    origin = headers.get("origin", "")
    if (event.get("httpMethod") or "POST").upper() == "OPTIONS":
        if not ALLOW_ORIGIN or ALLOW_ORIGIN == "*" or origin != ALLOW_ORIGIN:
            return _resp(403, {"error": "origin not allowed"}, origin=origin)
        return _resp(200, "", is_json=False, origin=origin)
    body = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True).decode()
    except Exception:
        return _resp(400, {"error": "invalid request body"}, origin=origin)
    if len(body.encode()) > MAX_BODY:
        return _resp(413, {"error": "request body too large"}, origin=origin)
    auth_error = _authorize(event, body)
    if auth_error:
        code, message = auth_error
        return _resp(code, {"error": message}, origin=origin)
    if not _rate_allowed(_source_ip(event)):
        return _resp(429, {"error": "too many requests"}, origin=origin)
    try:
        d = json.loads(body) if body else {}
    except (json.JSONDecodeError, TypeError):
        return _resp(400, {"error": "invalid JSON"}, origin=origin)
    op = d.get("op", "tts")
    sid, skey, token = _creds()
    if not sid or not skey:
        return _resp(500, {"error": "missing credentials"})
    try:
        if op == "tts":
            text = (d.get("text") or "").strip()
            if not text: return _resp(400, {"error": "no text"})
            return _resp(200, do_tts(sid, skey, token, text[:2000], int(d.get("voice") or DEFAULT_VOICE)))
        if op == "maimemo":
            maimemo_token = os.environ.get("MAIMEMO_TOKEN")
            if not maimemo_token:
                return _resp(500, {"error": "Maimemo is not configured"})
            word = (d.get("text") or "").strip()
            if not word:
                return _resp(400, {"error": "no word"})
            return _resp(200, do_maimemo(maimemo_token, word[:200]))
        if op == "get":
            if not d.get("key"): return _resp(400, {"error": "no key"})
            return _resp(200, do_get(sid, skey, token, d["key"]))
        if op == "put":
            if not d.get("key"): return _resp(400, {"error": "no key"})
            return _resp(200, do_put(sid, skey, token, d["key"], d.get("lib", [])))
        return _resp(400, {"error": "bad op"})
    except Exception as e:
        print("provider operation failed:", type(e).__name__, str(e)[:300])
        return _resp(502, {"error": "upstream service failed"}, origin=origin)
