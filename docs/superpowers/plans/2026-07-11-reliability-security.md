# Reliability and Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make daily delivery retry-safe and observable, validate and safely render AI content, and require a personal signed access code for private or paid SCF operations.

**Architecture:** Keep GitHub Pages public and move protected browser calls through one HMAC-signing helper. Add focused Python modules for article validation and delivery state, make SCF verify signed requests and origins, and make GitHub Actions test before running the daily job.

**Tech Stack:** Python 3.11 standard library, JavaScript Web Crypto, GitHub Actions, Tencent SCF, `unittest`.

---

## File map

- Create `article_validation.py`: validate and sanitize generated article data.
- Create `delivery_state.py`: atomically read/write per-date Feishu delivery state.
- Create `tests/test_article_validation.py`: schema and sanitizer tests.
- Create `tests/test_delivery.py`: Feishu and daily retry/duplicate behavior.
- Create `tests/test_build_security.py`: generated-script and markup safety tests.
- Create `tests/test_scf_security.py`: SCF authentication, origin, size, and throttling tests.
- Modify `get_article.py`: validate before persisting model output.
- Modify `build.py`: validate, sanitize, and serialize safely.
- Modify `push_feishu.py`: reject transport and business failures.
- Modify `daily.py`: use durable delivery state and stop stale fallback delivery.
- Modify `template.html`: access-code prompt and HMAC request helper.
- Modify `scf/index.py`: verify signatures, origins, request size, and rate limits.
- Modify `.github/workflows/daily.yml`: dependencies, tests, concurrency, and state commits.
- Create `requirements.txt`: pinned supported AI SDKs.
- Modify `SCF_DEPLOY.md` and `README.md`: deployment and recovery instructions.

### Task 1: Article validation and sanitization

**Files:**
- Create: `article_validation.py`
- Create: `tests/test_article_validation.py`
- Modify: `get_article.py`

- [ ] **Step 1: Write failing validator tests**

Add tests that call the desired API:

```python
from article_validation import ArticleValidationError, prepare_article

def test_prepare_article_rejects_wrong_date(self):
    data = valid_article()
    data["date"] = "2026-07-10"
    with self.assertRaisesRegex(ArticleValidationError, "date"):
        prepare_article(data, expected_date="2026-07-11")

def test_prepare_article_removes_event_handlers(self):
    data = valid_article()
    data["paragraphs"][0]["en"] = '<span class="kw" data-ipa="x" data-def="y" onclick="bad()">word</span><img src=x onerror=bad()>'
    clean = prepare_article(data, expected_date=data["date"])
    self.assertNotIn("onclick", clean["paragraphs"][0]["en"])
    self.assertNotIn("<img", clean["paragraphs"][0]["en"])
    self.assertIn("&lt;img", clean["paragraphs"][0]["en"])
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_article_validation -v`

Expected: import failure because `article_validation` does not exist.

- [ ] **Step 3: Implement the focused validator**

Implement:

```python
class ArticleValidationError(ValueError):
    pass

def prepare_article(data: dict, expected_date: str | None = None) -> dict:
    """Return a deep-copied, validated article with sanitized paragraph HTML."""
```

Use `datetime.date.fromisoformat`, `copy.deepcopy`, `html.parser.HTMLParser`, and explicit field checks. Preserve only `<span class="kw" data-ipa="..." data-def="...">`; escape all other tags. Require 7–12 paragraphs, non-empty core fields, and validate any supplied questions as four-option questions with integer answers `0..3`. Use a broad 500–1600 word guard so legitimate existing articles remain valid.

- [ ] **Step 4: Validate before writing AI output**

In `get_article.py`, replace direct persistence with:

```python
from article_validation import prepare_article

data = prepare_article(data, expected_date=a.date)
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_article_validation -v`

Expected: all validator tests pass.

Commit: `feat: validate and sanitize generated articles`

### Task 2: Safe page construction

**Files:**
- Create: `tests/test_build_security.py`
- Modify: `build.py`
- Modify: `template.html`

- [ ] **Step 1: Write failing build-security tests**

Build a temporary malicious article and assert:

```python
self.assertNotIn("</script><script>alert", page)
self.assertIn("\\u003c/script\\u003e", page)
self.assertNotIn("onerror=", page)
self.assertIn('const TTS_API = "https://example.test', page)
```

Also assert the template renders Chinese text with `textContent`, not concatenated `innerHTML`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_build_security -v`

Expected: malicious script text is present or serialization assertion fails.

- [ ] **Step 3: Implement safe serialization and rendering**

Add:

```python
def _json_for_script(value):
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
```

Call `prepare_article` in `build()`, serialize both article data and `TTS_API_URL` with `_json_for_script`, and change the template placeholder to `const TTS_API = __TTS_API__;`. Construct the Chinese paragraph element with `textContent`. Add a CSP meta tag limited to self, inline page script/style, HTTPS connections, and data/blob audio.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_build_security tests.test_article_validation -v`

Expected: all pass.

Commit: `fix: render generated articles safely`

### Task 3: Strict Feishu delivery and durable state

**Files:**
- Create: `delivery_state.py`
- Create: `tests/test_delivery.py`
- Modify: `push_feishu.py`
- Modify: `daily.py`

- [ ] **Step 1: Write failing delivery tests**

Define tests for the desired behavior:

```python
def test_push_raises_on_business_error(self):
    with patch("urllib.request.urlopen", return_value=response('{"code":19001,"msg":"bad"}')):
        with self.assertRaisesRegex(RuntimeError, "19001"):
            push_feishu.push("https://example.test", "", {})

def test_failed_push_does_not_mark_delivery(self):
    with self.assertRaises(RuntimeError):
        run_daily(..., push_fn=failing_push)
    self.assertFalse(is_pushed(state_dir, "2026-07-11"))

def test_successful_push_marks_and_duplicate_skips(self):
    run_daily(..., push_fn=recording_push)
    run_daily(..., push_fn=recording_push)
    self.assertEqual(1, len(calls))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_delivery -v`

Expected: missing state API and non-raising Feishu behavior.

- [ ] **Step 3: Implement delivery state**

Create:

```python
def is_pushed(state_dir: Path, date: str) -> bool: ...
def mark_pushed(state_dir: Path, date: str, article_date: str, url: str) -> Path: ...
```

Write JSON atomically with `tempfile.NamedTemporaryFile` and `os.replace`. Include `feishu_pushed`, `article_date`, `url`, and an ISO UTC timestamp.

- [ ] **Step 4: Make Feishu errors fatal**

Parse the response in `push_feishu.push`; raise `RuntimeError` for malformed JSON, nonzero `code`, or missing success indication. Let `urllib.error.HTTPError` and network errors propagate.

- [ ] **Step 5: Refactor the daily entry point for testability**

Add `run(args, *, push_fn=push_feishu.push, state_dir=ROOT / "state")`. Check `is_pushed` before work, remove the stale-article fallback, push once, then call `mark_pushed`. `--no-push` must not create delivery state.

- [ ] **Step 6: Run tests and commit**

Run: `python -m unittest tests.test_delivery -v`

Expected: all pass.

Commit: `fix: make daily delivery retry safe`

### Task 4: SCF request authentication and origin enforcement

**Files:**
- Create: `tests/test_scf_security.py`
- Modify: `scf/index.py`

- [ ] **Step 1: Write failing authentication tests**

Use `unittest.mock.patch.dict(os.environ, ...)`, reload the module, and create signed events. Cover valid requests plus missing signature, bad signature, timestamp older than 300 seconds, wrong origin, body over 16 KiB, and burst limit.

Core assertion:

```python
response = scf.main_handler(signed_event({"op": "get", "key": "abc"}), None)
self.assertNotEqual(401, response["statusCode"])
self.assertEqual(401, scf.main_handler(unsigned_event(), None)["statusCode"])
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_scf_security -v`

Expected: unsigned requests are currently accepted or reach provider logic.

- [ ] **Step 3: Implement verification helpers**

Add:

```python
def _expected_signature(access_key, timestamp, nonce, raw_body):
    digest = hashlib.sha256(raw_body.encode()).hexdigest()
    canonical = "%s\n%s\n%s" % (timestamp, nonce, digest)
    return hmac.new(access_key.encode(), canonical.encode(), hashlib.sha256).hexdigest()

def _authorize(event, raw_body, now=None): ...
```

Require `APP_ACCESS_KEY`, validate `Origin` against exact `ALLOW_ORIGIN`, compare signatures with `hmac.compare_digest`, enforce ±300 seconds, validate nonce format, and cap bodies at 16 KiB. Return 401/403/413/429 without provider calls. Do not include exception strings in public 502 responses.

- [ ] **Step 4: Add lightweight token-bucket protection**

Maintain a module-local dictionary keyed by request IP, with an environment-configurable burst and refill rate. Document that gateway throttling remains mandatory for distributed enforcement.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_scf_security -v`

Expected: all pass.

Commit: `feat: authenticate and limit SCF requests`

### Task 5: Browser access-code signing flow

**Files:**
- Create: `tests/test_frontend_auth.py`
- Modify: `template.html`

- [ ] **Step 1: Write a failing template contract test**

Assert the template contains `APP_ACCESS_KEY`, `crypto.subtle.importKey`, `HMAC`, `X-App-Timestamp`, `X-App-Nonce`, `X-App-Signature`, and removes the stored key after a 401 or 403.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_frontend_auth -v`

Expected: access-code signing symbols are absent.

- [ ] **Step 3: Implement one protected request helper**

Add JavaScript functions:

```javascript
function accessKey(){
  let key=localStorage.getItem('APP_ACCESS_KEY')||'';
  if(!key) key=(prompt('请输入个人访问码')||'').trim();
  if(key) localStorage.setItem('APP_ACCESS_KEY',key);
  return key;
}
async function protectedFetch(payload){
  // JSON.stringify once, SHA-256 body, HMAC canonical string, send exact body.
}
```

Route TTS and Maimemo calls through `protectedFetch`. On authentication failure, delete `APP_ACCESS_KEY`, show a clear toast, and keep browser speech fallback available.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_frontend_auth tests.test_interaction_template -v`

Expected: all pass.

Commit: `feat: sign protected browser requests`

### Task 6: Reproducible CI and workflow safety

**Files:**
- Create: `requirements.txt`
- Create: `tests/test_workflow_config.py`
- Modify: `.github/workflows/daily.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing workflow contract tests**

Assert the YAML text contains a `concurrency` group, `pip install -r requirements.txt` without `|| true`, a unit-test step before production, `compileall`, and `git add articles docs state`. Assert `.gitignore` includes `secret.txt`, `secret.env`, caches, zip packages, and generated SCF binaries.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_workflow_config -v`

Expected: missing concurrency, requirements installation, tests, and state commit assertions fail.

- [ ] **Step 3: Add pinned dependencies and harden workflow**

Add exact known-compatible OpenAI and Anthropic versions to `requirements.txt`. Add workflow-level concurrency, install dependencies without error suppression, run `python -m unittest discover -v` and `python -m compileall -q *.py scf/index.py`, then run daily. Commit `state/` alongside generated artifacts. Remove suppressed `git pull` errors and retry a rejected push with one explicit fetch/rebase attempt.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_workflow_config -v`

Expected: all pass.

Commit: `ci: test and serialize daily publishing`

### Task 7: Deployment documentation

**Files:**
- Modify: `SCF_DEPLOY.md`
- Modify: `README.md`

- [ ] **Step 1: Write documentation contract tests**

Extend `tests/test_workflow_config.py` to assert documentation mentions `APP_ACCESS_KEY`, exact `ALLOW_ORIGIN`, gateway throttling, access-code rotation, delivery state, and failure recovery.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_workflow_config -v`

Expected: required deployment instructions are absent.

- [ ] **Step 3: Update documentation**

Document generation of a 32-byte access code, SCF environment variables, frontend first-use behavior, Tencent gateway/function URL throttling, rotation consequences, Actions recovery, and the fact that public reading/browser speech stays available without a code.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_workflow_config -v`

Expected: all pass.

Commit: `docs: add secure deployment and recovery guide`

### Task 8: Full regression and build verification

**Files:**
- Modify if required: only files implicated by a failing verification.

- [ ] **Step 1: Run the complete test suite**

Run: `python -m unittest discover -v`

Expected: all tests pass with zero errors or failures.

- [ ] **Step 2: Run syntax verification**

Run: `python -m compileall -q *.py scf/index.py`

Expected: exit code 0.

- [ ] **Step 3: Run a real sample build**

Run: `TTS_API_URL=https://example.test/api python build.py articles/2026-07-11.json`

Expected: `docs/2026-07-11.html` and `docs/index.html` are produced without validation errors.

- [ ] **Step 4: Inspect repository state**

Run: `git status --short && git log --oneline --max-count=10`

Expected: only the intentionally regenerated sample pages are modified; restore them by rebuilding with the production URL if available, otherwise do not commit sample-only URL changes.

- [ ] **Step 5: Final implementation commit if needed**

Commit only verified, intentional changes with message: `chore: complete reliability and security hardening`.
