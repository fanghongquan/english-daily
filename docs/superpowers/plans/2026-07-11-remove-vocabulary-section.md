# Remove Vocabulary Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the standalone vocabulary summary while preserving inline keyword learning aids.

**Architecture:** Delete the unused section markup, styles, and JavaScript from the self-contained template, then rebuild the latest page.

**Tech Stack:** HTML/CSS, vanilla JavaScript, Python `unittest`.

---

### Task 1: Remove and verify

- [ ] Change `tests/test_reading_experience.py` to require that `vocab-sec`, `vocab-filter`, `collectVocabulary`, `vocab-play`, and `vocab-add` are absent while `.kw` and IPA behavior remain.
- [ ] Run the focused test and verify it fails against the current template.
- [ ] Remove standalone vocabulary markup, CSS, and JavaScript from `template.html`.
- [ ] Run the focused and complete suites.
- [ ] Rebuild `docs/2026-07-11.html` with the production TTS URL and validate generated scripts with Node.
- [ ] Commit, merge to `main`, push, wait for Pages deployment, and confirm the online page no longer contains `vocab-sec`.
