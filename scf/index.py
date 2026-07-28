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
from datetime import date

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


# ---------------- 阅读反馈与难度档案（纯函数） ----------------
DIFFICULTIES = {"easy", "balanced", "hard"}


def _default_profile():
    return {
        "profile_version": 1,
        "target_mode": "balanced",
        "ability_score": 50.0,
        "base_score": 50.0,
        "observation_count": 0,
        "observed_dates": [],
        "target_words": 900,
        "target_new_words": 6,
        "sentence_level": 3,
        "target_comprehension": "85%-90%",
        "trend": "stable",
        "recent": [],
        "updated_at": None,
    }


def _bounded_int(value, name, low, high, allow_none=False):
    if allow_none and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer" % name)
    if value < low or value > high:
        raise ValueError("%s out of range" % name)
    return value


def _normalize_feedback(payload, now):
    if not isinstance(payload, dict):
        raise ValueError("feedback must be an object")
    article_date = payload.get("article_date")
    if not isinstance(article_date, str):
        raise ValueError("invalid article_date")
    try:
        if date.fromisoformat(article_date).isoformat() != article_date:
            raise ValueError
    except ValueError:
        raise ValueError("invalid article_date")
    difficulty = payload.get("difficulty")
    if difficulty is not None and difficulty not in DIFFICULTIES:
        raise ValueError("invalid difficulty")
    completed = payload.get("completed", False)
    if not isinstance(completed, bool):
        raise ValueError("completed must be boolean")
    quiz_total = _bounded_int(payload.get("quiz_total", 0),
                              "quiz_total", 0, 10)
    quiz_score = _bounded_int(payload.get("quiz_first_score"),
                              "quiz_first_score", 0, quiz_total,
                              allow_none=True)
    if (quiz_score is None and quiz_total != 0) or (
            quiz_score is not None and quiz_total == 0):
        raise ValueError("quiz score and total do not match")
    return {
        "article_date": article_date,
        "difficulty": difficulty,
        "completed": completed,
        "quiz_first_score": quiz_score,
        "quiz_total": quiz_total,
        "word_action_count": _bounded_int(
            payload.get("word_action_count", 0),
            "word_action_count", 0, 100),
        "phrase_action_count": _bounded_int(
            payload.get("phrase_action_count", 0),
            "phrase_action_count", 0, 100),
        "updated_at": now,
    }


def _merge_feedback(existing, incoming, now):
    new = _normalize_feedback(incoming, now)
    if not existing:
        return new
    old = _normalize_feedback(existing, existing.get("updated_at") or now)
    if old["article_date"] != new["article_date"]:
        raise ValueError("article dates do not match")
    return {
        "article_date": new["article_date"],
        "difficulty": (new["difficulty"] if new["difficulty"] is not None
                       else old["difficulty"]),
        "completed": old["completed"] or new["completed"],
        "quiz_first_score": (
            old["quiz_first_score"] if old["quiz_first_score"] is not None
            else new["quiz_first_score"]),
        "quiz_total": (
            old["quiz_total"] if old["quiz_first_score"] is not None
            else new["quiz_total"]),
        "word_action_count": max(old["word_action_count"],
                                 new["word_action_count"]),
        "phrase_action_count": max(old["phrase_action_count"],
                                   new["phrase_action_count"]),
        "updated_at": now,
    }


def _vocabulary_signal(total):
    if total <= 3:
        return 1.0
    if total == 4:
        return 0.5
    if total <= 8:
        return 0.0
    if total <= 10:
        return -0.5
    return -1.0


def _event_signal(event):
    signal = 0.0
    difficulty = event.get("difficulty")
    if difficulty is not None:
        signal += {"easy": 1.0, "balanced": 0.0, "hard": -1.0}[difficulty] * 0.5
    score, total = event.get("quiz_first_score"), event.get("quiz_total", 0)
    if score is not None and total:
        ratio = score / float(total)
        signal += (1.0 if ratio >= 0.85 else -1.0 if ratio < 0.6 else 0.0) * 0.25
    actions = event.get("word_action_count", 0) + event.get("phrase_action_count", 0)
    signal += _vocabulary_signal(actions) * 0.2
    signal += (1.0 if event.get("completed") else -1.0) * 0.05
    return max(-1.0, min(1.0, round(signal, 6)))


def _clamp(value, low, high):
    return max(low, min(high, value))


def _apply_profile_targets(profile):
    score = profile["ability_score"]
    profile["target_words"] = int(_clamp(
        round((900 + (score - 50) * 25) / 50) * 50, 700, 1100))
    profile["target_new_words"] = int(_clamp(
        round(6 + (score - 50) / 10), 5, 8))
    profile["sentence_level"] = int(_clamp(
        round(3 + (score - 50) / 10), 1, 5))
    recent = profile["recent"]
    if recent:
        weights = list(range(1, len(recent) + 1))
        weighted = sum(item["signal"] * weight
                       for item, weight in zip(recent, weights)) / sum(weights)
    else:
        weighted = 0.0
    profile["trend"] = (
        "harder" if weighted > 0.2 else
        "easier" if weighted < -0.2 else "stable")
    return profile


def _update_profile(profile, event, now, previous_event=None):
    source = profile if isinstance(profile, dict) else {}
    base = float(source.get("base_score", 50.0))
    count = int(source.get("observation_count", 0))
    recent = [
        {
            "article_date": item["article_date"],
            "signal": float(item["signal"]),
            "step": float(item["step"]),
        }
        for item in source.get("recent", [])
        if isinstance(item, dict)
        and isinstance(item.get("article_date"), str)
        and isinstance(item.get("signal"), (int, float))
        and isinstance(item.get("step"), (int, float))
    ]
    observed_dates = []
    for article_date in source.get("observed_dates", []):
        if isinstance(article_date, str) and article_date not in observed_dates:
            observed_dates.append(article_date)
    if not observed_dates and count <= len(recent):
        observed_dates = [item["article_date"] for item in recent]
    signal = _event_signal(event)
    matching = next((item for item in recent
                     if item["article_date"] == event["article_date"]), None)
    if matching:
        matching["signal"] = signal
    elif event["article_date"] in observed_dates:
        if previous_event is not None:
            old_signal = _event_signal(previous_event)
            date_index = observed_dates.index(event["article_date"])
            step = 1.0 if date_index < 3 else 2.0
            base = _clamp(
                base + (signal - old_signal) * step, 20.0, 80.0)
    else:
        observed_dates.append(event["article_date"])
        recent.append({
            "article_date": event["article_date"],
            "signal": signal,
            "step": 1.0 if count < 3 else 2.0,
        })
        recent.sort(key=lambda item: item["article_date"])
        count += 1
    count = max(count, len(observed_dates))
    while len(recent) > 7:
        oldest = recent.pop(0)
        base = _clamp(base + oldest["signal"] * oldest["step"], 20.0, 80.0)
    ability = base
    for item in recent:
        ability = _clamp(ability + item["signal"] * item["step"], 20.0, 80.0)
    result = _default_profile()
    result.update({
        "base_score": round(base, 3),
        "ability_score": round(ability, 3),
        "observation_count": count,
        "observed_dates": observed_dates,
        "recent": recent,
        "updated_at": now,
    })
    return _apply_profile_targets(result)


# ---------------- COS 读写 (q-signature, 用于同步) ----------------
def _cos_auth(method, path, sid, skey):
    now = int(time.time()); kt = "%d;%d" % (now, now + 600)
    signkey = hmac.new(skey.encode(), kt.encode(), hashlib.sha1).hexdigest()
    httpstr = "%s\n%s\n\n%s\n" % (method.lower(), path, "")  # 无 query、不签 header
    s2s = "sha1\n%s\n%s\n" % (kt, hashlib.sha1(httpstr.encode()).hexdigest())
    sig = hmac.new(signkey.encode(), s2s.encode(), hashlib.sha1).hexdigest()
    return ("q-sign-algorithm=sha1&q-ak=%s&q-sign-time=%s&q-key-time=%s"
            "&q-header-list=&q-url-param-list=&q-signature=%s") % (sid, kt, kt, sig)


def _cos_req(method, objkey, sid, skey, token, body=None,
             extra_headers=None, with_meta=False):
    bucket = os.environ.get("COS_BUCKET"); region = os.environ.get("COS_REGION", "ap-guangzhou")
    if not bucket: raise RuntimeError("COS_BUCKET not set")
    host = "%s.cos.%s.myqcloud.com" % (bucket, region)
    path = "/" + objkey
    h = {"Authorization": _cos_auth(method, path, sid, skey), "Host": host}
    if token: h["x-cos-security-token"] = token
    if body is not None: h["Content-Type"] = "application/json"
    h.update(extra_headers or {})
    req = urllib.request.Request("https://" + host + path, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
        return (data, r.headers.get("ETag")) if with_meta else data


PROFILE_KEY = "learning-profile/profile.json"


def _feedback_key(article_date):
    return "learning-profile/events/%s.json" % article_date


def _cos_json_get_with_etag(objkey, sid, skey, token):
    try:
        raw, etag = _cos_req(
            "GET", objkey, sid, skey, token, with_meta=True)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        raise
    data = json.loads(raw.decode())
    if not isinstance(data, dict):
        raise ValueError("stored JSON must be an object")
    if not etag:
        raise RuntimeError("COS response missing ETag")
    return data, etag


def _cos_json_get(objkey, sid, skey, token):
    return _cos_json_get_with_etag(objkey, sid, skey, token)[0]


_NO_PRECONDITION = object()


def _cos_json_put(objkey, data, sid, skey, token,
                  etag=_NO_PRECONDITION):
    body = json.dumps(
        data, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {}
    if etag is None:
        headers["If-None-Match"] = "*"
    elif etag is not _NO_PRECONDITION:
        headers["If-Match"] = etag
    _cos_req("PUT", objkey, sid, skey, token, body,
             extra_headers=headers)


def _public_profile(profile):
    allowed = (
        "profile_version", "target_mode", "ability_score",
        "observation_count", "target_words", "target_new_words",
        "sentence_level", "target_comprehension", "trend", "updated_at",
    )
    return {key: profile[key] for key in allowed if key in profile}


def do_feedback_put(sid, skey, token, payload, now=None):
    now = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    normalized = _normalize_feedback(payload, now)
    article_date = normalized["article_date"]
    event_key = _feedback_key(article_date)
    for _attempt in range(5):
        existing, event_etag = _cos_json_get_with_etag(
            event_key, sid, skey, token)
        merged = _merge_feedback(existing, normalized, now)
        profile, profile_etag = _cos_json_get_with_etag(
            PROFILE_KEY, sid, skey, token)
        updated = _update_profile(
            profile or _default_profile(), merged, now,
            previous_event=existing)
        try:
            _cos_json_put(
                event_key, merged, sid, skey, token, etag=event_etag)
            _cos_json_put(
                PROFILE_KEY, updated, sid, skey, token, etag=profile_etag)
            return {"ok": True, "profile": _public_profile(updated)}
        except urllib.error.HTTPError as error:
            if error.code not in (409, 412):
                raise
    raise RuntimeError("feedback update conflict")


def do_profile_get(sid, skey, token):
    profile = _cos_json_get(PROFILE_KEY, sid, skey, token) or _default_profile()
    return {"profile": _public_profile(profile)}


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


def _authorize_profile(event):
    configured = os.environ.get("PROFILE_READ_TOKEN", "")
    if len(configured) < 32:
        return 500, "server authentication is not configured"
    supplied = _headers(event).get("x-profile-token", "")
    if not supplied or not hmac.compare_digest(configured, supplied):
        return 401, "invalid server token"
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
    try:
        parsed = json.loads(body) if body else {}
    except (json.JSONDecodeError, TypeError):
        parsed = None
    op = parsed.get("op", "tts") if isinstance(parsed, dict) else None
    auth_error = (
        _authorize_profile(event) if op == "profile_get"
        else _authorize(event, body))
    if auth_error:
        code, message = auth_error
        return _resp(code, {"error": message}, origin=origin)
    rate_key = ("profile:" if op == "profile_get" else "browser:") + _source_ip(event)
    if not _rate_allowed(rate_key):
        return _resp(429, {"error": "too many requests"}, origin=origin)
    if parsed is None:
        return _resp(400, {"error": "invalid JSON"}, origin=origin)
    if not isinstance(parsed, dict):
        return _resp(400, {"error": "JSON body must be an object"}, origin=origin)
    d = parsed
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
        if op == "feedback_put":
            try:
                _normalize_feedback(
                    d, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            except ValueError as error:
                return _resp(400, {"error": str(error)[:160]}, origin=origin)
            return _resp(200, do_feedback_put(sid, skey, token, d))
        if op == "profile_get":
            return _resp(200, do_profile_get(sid, skey, token))
        return _resp(400, {"error": "bad op"})
    except Exception as e:
        print("provider operation failed:", type(e).__name__, str(e)[:300])
        return _resp(502, {"error": "upstream service failed"}, origin=origin)
