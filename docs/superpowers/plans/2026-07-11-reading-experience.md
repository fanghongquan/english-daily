# Mobile Reading Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hybrid mobile toolbar, local reading progress, paragraph narration, automatic vocabulary review, and scored quizzes to every generated reading page.

**Architecture:** Preserve the self-contained `template.html` architecture and organize the browser code into small state, speech, vocabulary, and quiz functions. Validate behavior through generated-page contract tests and a real latest-article build.

**Tech Stack:** HTML/CSS, vanilla JavaScript, Web Speech/Audio APIs, `localStorage`, Python `unittest`.

---

### Task 1: Responsive toolbar and accessibility foundation

**Files:**
- Create: `tests/test_reading_experience.py`
- Modify: `template.html`

- [ ] Write failing tests requiring `#read-progress`, `#mobile-float`, `#mobile-more`, safe-area CSS, the 640px breakpoint, `focus-visible`, explicit rate/voice labels, `lang="en-US"`, `lang="zh-CN"`, and `aria-pressed` updates.
- [ ] Run `python -m unittest tests.test_reading_experience -v` and verify the required markers are absent.
- [ ] Add the top progress bar, mobile floating speech/more control, collapsible settings panel, responsive CSS, safe-area spacing, labels, language attributes, focus styles, and reduced-motion rule.
- [ ] Run the focused test and existing template tests; commit as `feat: add accessible mobile reading controls`.

Core markup contract:

```html
<div id="read-progress" role="progressbar" aria-label="阅读进度"></div>
<div id="mobile-float"><button id="mobile-play">▶ 朗读</button><button id="mobile-more">•••</button></div>
<div id="mobile-panel" hidden>...</div>
```

### Task 2: Durable local reading progress

**Files:**
- Modify: `tests/test_reading_experience.py`
- Modify: `template.html`

- [ ] Add failing tests for `englishDaily:progress:`, `loadProgress`, `saveProgress`, throttled scroll handling, `continue-reading`, `从头开始`, completion threshold, and progressbar ARIA values.
- [ ] Run the focused test and verify RED.
- [ ] Implement defensive JSON storage, a versioned article record, scroll ratio/paragraph tracking, 92% completion, a non-blocking resume banner, continue/reset actions, and throttled updates.
- [ ] Run focused and full tests; commit as `feat: persist local reading progress`.

Desired record:

```javascript
{version:1,ratio:0.42,lastParagraph:3,completed:false,quizScore:null,quizTotal:0,updatedAt:"..."}
```

### Task 3: Paragraph narration and unified speech state

**Files:**
- Modify: `tests/test_reading_experience.py`
- Modify: `template.html`

- [ ] Add failing tests requiring `朗读本段`, `data-paragraph`, `activeParagraph`, `setSpeakingState`, `aria-current`, nearest-visible-paragraph selection, and mobile play/stop wiring.
- [ ] Run the focused test and verify RED.
- [ ] Add one speech button per paragraph, track the active paragraph, highlight it during playback, cancel previous playback before starting another, and connect the floating control to the nearest visible paragraph. Preserve browser fallback.
- [ ] Run focused and existing interaction/auth tests; commit as `feat: add paragraph narration controls`.

### Task 4: Automatic vocabulary list

**Files:**
- Modify: `tests/test_reading_experience.py`
- Modify: `template.html`

- [ ] Add failing tests for `#vocab-sec`, `#vocab-filter`, `collectVocabulary`, lowercase de-duplication, occurrence count, `vocab-play`, and `vocab-add` actions.
- [ ] Run the focused test and verify RED.
- [ ] Derive unique vocabulary from rendered `.kw` nodes, render word/IPA/definition/count rows, filter locally, use `play()` for speech, and `doAdd()` for Maimemo. Hide the section when no keywords exist.
- [ ] Run focused and full tests; commit as `feat: build vocabulary review from article keywords`.

Desired normalized entry:

```javascript
{word:"foundation",ipa:"...",definition:"基础",count:2}
```

### Task 5: Quiz scoring and persistence

**Files:**
- Modify: `tests/test_reading_experience.py`
- Modify: `template.html`

- [ ] Add failing tests for `#quiz-summary`, `quizScore`, `answeredCount`, incorrect question tracking, `只看错题`, `重新作答`, and persistence through `saveProgress`.
- [ ] Run the focused test and verify RED.
- [ ] Track selected answers, update score after every answer, show percentage and incorrect question numbers after completion, implement incorrect-only filtering and full reset, and persist the final score/total in the progress record.
- [ ] Run focused and full tests; commit as `feat: score and review comprehension quizzes`.

### Task 6: Archive completion indicators

**Files:**
- Modify: `tests/test_reading_experience.py`
- Modify: `build.py`

- [ ] Add a failing test requiring archive rows to expose `data-date` and archive JavaScript to read `englishDaily:progress:` and append an “已读” badge for completed records.
- [ ] Run the focused test and verify RED.
- [ ] Add stable date attributes and progressive completion badges; ignore malformed storage and keep the archive usable with JavaScript disabled.
- [ ] Run focused and build-security tests; commit as `feat: show completed articles in archive`.

### Task 7: Full build, regression, merge, and publish

**Files:**
- Regenerate: `docs/2026-07-11.html`

- [ ] Run `python -m unittest discover -v` and require zero failures.
- [ ] Run `python -m compileall -q *.py scf/index.py` and require exit 0.
- [ ] Rebuild with the production `TTS_API_URL` and verify `docs/2026-07-11.html` contains no placeholders.
- [ ] Parse every generated `<script>` with `new Function` under Node and require no syntax errors.
- [ ] Commit the regenerated latest page, merge into `main`, repeat the full verification, push GitHub, wait for Pages deployment, and confirm the online page contains the new progress, vocabulary, paragraph speech, and quiz summary markers.
