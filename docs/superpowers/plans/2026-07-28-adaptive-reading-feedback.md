# Adaptive Reading Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure, mobile-first feedback loop that turns reading behavior into bounded DeepSeek difficulty parameters for the next daily article.

**Architecture:** The static reader records a three-level rating plus objective signals and sends only aggregate counts to the existing protected SCF. SCF validates, idempotently merges, stores events and a rolling profile in private COS, while GitHub Actions reads the derived profile through a separate server token and falls back to a balanced default if unavailable.

**Tech Stack:** Python 3 standard library, Tencent SCF/COS, vanilla HTML/CSS/JavaScript, GitHub Actions, unittest.

**Cost guard:** Reuse the existing SCF function, COS bucket, public GitHub repository and single daily DeepSeek request. Do not buy plans, create cloud resources, add model calls, enable larger runners or accept any billing/upgrade prompt. Personalization failures must fall back to the balanced default.

---

## File structure

- Create `profile_client.py`: failure-safe server-side profile reader used by article generation.
- Modify `scf/index.py`: feedback validation, rolling profile calculation, COS persistence, browser/server auth routing.
- Modify `template.html`: mobile feedback card, local state, first-score capture, action counters, pending sync queue.
- Modify `get_article.py`: profile-aware prompt constraints.
- Modify `.github/workflows/daily.yml`: profile URL/token injection.
- Modify `SCF_DEPLOY.md` and `README.md`: deployment variables, rotation, recovery, and behavior.
- Create `tests/test_learning_profile.py`: deterministic calculator and merge tests.
- Create `tests/test_profile_client.py`: API success and fallback tests.
- Modify `tests/test_scf_security.py`: auth/routing tests.
- Modify `tests/test_reading_experience.py`: frontend contract tests.
- Modify `tests/test_generation_retry.py`: profile prompt tests.
- Modify `tests/test_workflow_config.py`: workflow/deployment contract tests.

### Task 1: Deterministic learning profile engine

**Files:**
- Modify: `scf/index.py`
- Create: `tests/test_learning_profile.py`

- [ ] **Step 1: Write failing merge and scoring tests**

Add tests covering valid feedback normalization, invalid values, first quiz score preservation, monotonic completion, maximum action counts, subjective replacement, no-subjective low-weight signal, calibration step, seven-record rollover, same-date recomputation, and derived target bounds.

Core expected examples:

```python
event = scf._merge_feedback(None, {
    "article_date": "2026-07-28",
    "difficulty": "easy",
    "completed": True,
    "quiz_first_score": 4,
    "quiz_total": 4,
    "word_action_count": 2,
    "phrase_action_count": 0,
}, now="2026-07-28T00:00:00Z")
self.assertGreater(scf._event_signal(event), 0)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest -v tests.test_learning_profile`

Expected: failure because `_merge_feedback`, `_event_signal`, and `_update_profile` do not exist.

- [ ] **Step 3: Implement minimal pure functions**

In `scf/index.py`, add:

```python
DIFFICULTIES = {"easy", "balanced", "hard"}

def _default_profile():
    return {
        "profile_version": 1, "target_mode": "balanced",
        "ability_score": 50.0, "base_score": 50.0,
        "observation_count": 0,
        "target_words": 900, "target_new_words": 6,
        "sentence_level": 3, "target_comprehension": "85%-90%",
        "trend": "stable", "recent": [], "updated_at": None,
    }
```

Implement strict scalar validation, merge semantics from the design, weighted signal calculation, calibration rate, recent-window rollover and target derivation. Clamp counts and scores instead of accepting invalid types; reject invalid dates, difficulty labels and score relationships with `ValueError`.

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
python3 -m unittest -v tests.test_learning_profile
python3 -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scf/index.py tests/test_learning_profile.py
git commit -m "feat: add adaptive difficulty profile engine"
```

### Task 2: COS persistence and authenticated SCF operations

**Files:**
- Modify: `scf/index.py`
- Modify: `tests/test_scf_security.py`
- Modify: `tests/test_learning_profile.py`

- [ ] **Step 1: Write failing persistence and routing tests**

Test `feedback_put` browser-HMAC routing, `profile_get` server-token routing, rejection of missing/bad server token, feedback field validation returning 400, COS 404 default behavior, and event/profile PUT calls.

Example routing contract:

```python
with patch.object(scf, "do_feedback_put", return_value={"ok": True}) as operation:
    response = scf.main_handler(signed_event({
        "op": "feedback_put", "article_date": "2026-07-28",
        "difficulty": "balanced", "completed": True,
        "quiz_first_score": 3, "quiz_total": 4,
        "word_action_count": 6, "phrase_action_count": 1,
    }), None)
self.assertEqual(200, response["statusCode"])
operation.assert_called_once()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest -v tests.test_scf_security tests.test_learning_profile`

Expected: failure because the operations and server-token route are missing.

- [ ] **Step 3: Implement COS JSON helpers and operations**

Add fixed private keys:

```python
PROFILE_KEY = "learning-profile/profile.json"
OBSERVATION_PREFIX = "learning-profile/observations/"

def _feedback_key(article_date):
    return "learning-profile/events/%s.json" % article_date
```

Implement `_cos_json_get`, `_cos_json_put`, COS prefix listing, immutable observation keys, `do_feedback_put`, and `do_profile_get`. New feedback writes a self-contained encoded observation key, then the bounded profile is deterministically rebuilt from all legacy events and observations. A missing profile returns the default; other provider errors propagate to the existing sanitized 502 response.

- [ ] **Step 4: Implement separate server authentication**

Parse the bounded JSON body before choosing the auth path. For `profile_get`, require a constant-time comparison against `PROFILE_READ_TOKEN` supplied in `x-profile-token`, skip browser origin/HMAC, and retain rate limiting under a separate key. All other operations continue through `_authorize`.

Update CORS allowed headers only with headers required by browser calls; do not expose the server token to browser code.

- [ ] **Step 5: Run focused and full tests**

Run:

```bash
python3 -m unittest -v tests.test_scf_security tests.test_learning_profile
python3 -m unittest discover -v
python3 -m compileall -q *.py scf/index.py
```

Expected: all tests and compilation pass.

- [ ] **Step 6: Commit**

```bash
git add scf/index.py tests/test_scf_security.py tests/test_learning_profile.py
git commit -m "feat: persist learning feedback in COS"
```

### Task 3: Failure-safe profile client and DeepSeek prompt

**Files:**
- Create: `profile_client.py`
- Create: `tests/test_profile_client.py`
- Modify: `get_article.py`
- Modify: `tests/test_generation_retry.py`

- [ ] **Step 1: Write failing client tests**

Test a valid JSON response, missing environment variables, HTTP failure, invalid JSON, invalid profile fields and timeout. All failure cases must return an independent default profile without raising.

```python
with patch("urllib.request.urlopen", return_value=FakeResponse(valid_body)):
    profile = profile_client.fetch_profile(
        "https://profile.test", "server-token-of-at-least-32-bytes")
self.assertEqual(950, profile["target_words"])
```

- [ ] **Step 2: Write failing prompt tests**

Patch `profile_client.load_profile_from_env` and verify `_build_prompt` contains exact word, new-word, sentence-level, comprehension and trend constraints.

- [ ] **Step 3: Run tests and verify RED**

Run: `python3 -m unittest -v tests.test_profile_client tests.test_generation_retry`

Expected: import/function/assertion failures for the new behavior.

- [ ] **Step 4: Implement `profile_client.py`**

Use `urllib.request.Request` with POST body `{"op":"profile_get"}`, `x-profile-token`, JSON content type and a 10-second timeout. Validate only the bounded fields consumed by generation. Never print the token or raw response. Return a fresh default on every failure.

- [ ] **Step 5: Add profile constraints to `get_article.py`**

Change `_build_prompt(date, profile=None)` to load the environment profile when omitted and append a dedicated learner-target block. Keep existing topic/history behavior and validation retries unchanged.

- [ ] **Step 6: Run focused and full tests**

Run:

```bash
python3 -m unittest -v tests.test_profile_client tests.test_generation_retry
python3 -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add profile_client.py get_article.py tests/test_profile_client.py tests/test_generation_retry.py
git commit -m "feat: personalize DeepSeek reading targets"
```

### Task 4: Mobile feedback card and local queue

**Files:**
- Modify: `template.html`
- Modify: `tests/test_reading_experience.py`
- Modify: `tests/test_frontend_auth.py`

- [ ] **Step 1: Write failing frontend contract tests**

Require the three buttons and accessible pressed state, 48px touch size, feedback status live region, pending queue key, first quiz score, non-interactive stored-key check, aggregate-only payload fields, action counters and retry triggers.

Contract markers include:

```python
for marker in (
    'id="difficulty-feedback"', 'data-value="easy"',
    'data-value="balanced"', 'data-value="hard"',
    "englishDaily:feedback:pending", "quizFirstScore",
    "word_action_count", "phrase_action_count",
    "function syncLearningFeedback", "aria-live=\"polite\"",
):
    self.assertIn(marker, html)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest -v tests.test_reading_experience tests.test_frontend_auth`

Expected: missing feedback contract markers.

- [ ] **Step 3: Implement the feedback card and style**

Place the card after `quiz-sec`. Reuse existing CSS variables, use one restrained signature element: a three-segment “difficulty balance” control whose selected segment fills with the existing accent color. Preserve dark mode, 48px targets, keyboard focus and reduced motion.

- [ ] **Step 4: Extend local progress and first-score behavior**

Initialize absent fields compatibly. On first complete quiz, set `quizFirstScore` only if null; resetting the quiz clears the current attempt but not the first score. Track unique local action keys and upload only counts.

- [ ] **Step 5: Implement pending sync**

Build a date-keyed pending queue. `syncLearningFeedback(false)` must return without prompting if no stored access key. `syncLearningFeedback(true)` may call the existing access-key prompt. Successful responses clear pending state and render the server trend; failures preserve pending state.

Trigger low-priority sync after quiz completion, 92% reading completion, page load with pending data, and successful word/phrase action. Debounce automatic calls.

- [ ] **Step 6: Run focused and full tests**

Run:

```bash
python3 -m unittest -v tests.test_reading_experience tests.test_frontend_auth
python3 -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add template.html tests/test_reading_experience.py tests/test_frontend_auth.py
git commit -m "feat: add mobile reading difficulty feedback"
```

### Task 5: Workflow and deployment documentation

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `tests/test_workflow_config.py`
- Modify: `SCF_DEPLOY.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing workflow/documentation tests**

Require:

```yaml
PROFILE_API_URL: ${{ vars.TTS_API_URL }}
PROFILE_READ_TOKEN: ${{ secrets.PROFILE_READ_TOKEN }}
```

Require docs to describe `PROFILE_READ_TOKEN`, private COS objects, rotation, default fallback, and feedback privacy.

- [ ] **Step 2: Run test and verify RED**

Run: `python3 -m unittest -v tests.test_workflow_config`

Expected: missing workflow variables and documentation markers.

- [ ] **Step 3: Update workflow and docs**

Inject both variables only into `Generate + build`. Do not expose the server token to rendered HTML or later steps. Document generating a 32-byte token, setting the same value in SCF and GitHub Secret, deployment rollback, and COS IAM requirements.

- [ ] **Step 4: Run full static verification**

Run:

```bash
python3 -m unittest discover -v
python3 -m compileall -q *.py scf/index.py
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/daily.yml"); puts "workflow yaml ok"'
git diff --check
```

Expected: all tests pass, YAML parses, no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily.yml tests/test_workflow_config.py SCF_DEPLOY.md README.md
git commit -m "docs: configure adaptive profile delivery"
```

### Task 6: Browser-level mobile verification

**Files:**
- Generated: `docs/2026-07-28.html` in a temporary verification copy only
- Modify only if verification reveals a defect: `template.html`

- [ ] **Step 1: Build a current article**

Run: `python3 build.py articles/2026-07-28.json`

Expected: generated page contains `difficulty-feedback`.

- [ ] **Step 2: Serve locally**

Run: `python3 -m http.server 8765 --directory docs`

Expected: local site responds at `/2026-07-28.html`.

- [ ] **Step 3: Verify at mobile width**

Using browser automation at 390×844:

- Scroll to feedback card.
- Verify three controls fit without horizontal scrolling.
- Complete the quiz and confirm first score persists through reset.
- Select each difficulty and confirm only one pressed state.
- Simulate failed network and confirm pending status.
- Verify keyboard focus and dark mode.

- [ ] **Step 4: Re-run tests after UI fixes**

Run: `python3 -m unittest discover -v`

Expected: all tests pass.

### Task 7: Review, publish, cloud configuration, and live verification

**Files:**
- No new source files unless review finds a defect.

- [ ] **Step 1: Request independent code review**

Review the complete diff from `origin/main` to branch HEAD for security, idempotency, mobile behavior, profile math, workflow secret exposure and backward compatibility. Resolve every Critical and Important finding.

- [ ] **Step 2: Fresh final verification**

Run the complete test, compile, YAML, `git diff --check`, and mobile browser suite again. Record exact counts.

- [ ] **Step 3: Push and merge through PR**

Push `agent/adaptive-reading-feedback`, create a draft PR with root cause/design/checks, mark ready after review, and merge to `main`.

- [ ] **Step 4: Configure secrets**

Generate one high-entropy token without printing it. Set it as GitHub Actions Secret `PROFILE_READ_TOKEN` and SCF environment variable `PROFILE_READ_TOKEN`. Preserve all existing SCF variables.

- [ ] **Step 5: Deploy SCF**

Deploy the reviewed `scf/index.py` to the existing function through the authenticated Tencent Cloud console or established deployment method. Do not create a function, bucket, package or paid service. Stop if the console asks to purchase, upgrade or confirm billing. Read back the function configuration and verify the code version/environment values without exposing secrets.

- [ ] **Step 6: Verify production API**

Submit one synthetic calibration feedback for the current article using browser HMAC, read it back with the server token, confirm idempotent update, then replace it with the actual neutral baseline or remove the synthetic event before handoff.

- [ ] **Step 7: Verify live Pages**

Trigger the daily workflow only if needed to publish a page containing the new component. Confirm live HTML has the feedback card, submit a neutral real feedback, and verify `profile_get` returns the updated balanced profile.

- [ ] **Step 8: Final handoff**

Report PR, merge commit, test count, live URL, API verification, profile trend, and any non-blocking platform warnings.
