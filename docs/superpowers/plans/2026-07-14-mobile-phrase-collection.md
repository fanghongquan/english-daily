# Mobile Phrase Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mobile-first phrase-selection mode that saves a continuous 2–10 word phrase without invoking the browser's native selection menu.

**Architecture:** Extend the existing `.tok` model and `#selbar` controller in `template.html`. Preserve direct double-click word collection, while an explicit phrase state machine selects two tokens from one paragraph, previews the normalized range in a fixed bottom bar, and submits it through `doAdd()`.

**Tech Stack:** Self-contained HTML/CSS/vanilla JavaScript, Python `unittest`, `build.py`, GitHub Pages.

---

## File Structure

- Modify `template.html`: toolbar markup/styles and phrase-selection state machine.
- Modify `tests/test_interaction_template.py`: interaction contract and regression checks.
- Regenerate `docs/2026-07-11.html`: latest published article.
- Regenerate `docs/index.html`: normal build output, expected to be mechanically unchanged.

### Task 1: Define the interaction contract

**Files:**
- Modify: `tests/test_interaction_template.py`

- [ ] **Step 1: Write a failing phrase contract test**

Add this helper and test while retaining the existing native-selection regression checks:

```python
def assert_phrase_collection(self, html):
    self.assertIn('id="sel-phrase"', html)
    self.assertIn('id="phrase-add"', html)
    self.assertIn('id="phrase-cancel"', html)
    self.assertIn("function enterPhraseMode", html)
    self.assertIn("function selectPhraseEnd", html)
    self.assertIn("function phraseFromTokens", html)
    self.assertIn("start.closest('.en')!==end.closest('.en')", html)
    self.assertIn("selected.length<2", html)
    self.assertIn("selected.length>10", html)
    self.assertIn("replace(/^[^A-Za-z]+|[^A-Za-z]+$/g", html)
    self.assertIn("短语需在同一段内", html)
    self.assertIn("短语最多 10 个词", html)
    self.assertIn("function exitPhraseMode", html)
    self.assertIn("doAdd(selText)", html)
    self.assertIn("env(safe-area-inset-bottom)", html)
    self.assertNotIn("window.getSelection", html)

def test_template_supports_phrase_collection(self):
    self.assert_phrase_collection(self.read("template.html"))
```

- [ ] **Step 2: Run the focused test**

Run `python -m unittest tests.test_interaction_template.InteractionTemplateTest.test_template_supports_phrase_collection -v`.

Expected: `FAIL` because the phrase controls do not exist.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_interaction_template.py
git commit -m "test: define mobile phrase collection contract"
```

### Task 2: Add responsive toolbar states

**Files:**
- Modify: `template.html`
- Test: `tests/test_interaction_template.py`

- [ ] **Step 1: Replace the single-action toolbar markup**

```html
<div id="selbar" role="toolbar" aria-live="polite">
  <span id="phrase-preview"></span>
  <span id="phrase-hint"></span>
  <button id="sel-add">＋ 单词</button>
  <button id="sel-phrase">选择短语</button>
  <button id="phrase-add">＋ 短语</button>
  <button id="phrase-cancel">取消</button>
</div>
```

- [ ] **Step 2: Add state-dependent CSS**

```css
.tok.phrase-selected{background:color-mix(in srgb,var(--accent) 18%,transparent);border-radius:4px}
#phrase-preview,#phrase-hint,#phrase-add,#phrase-cancel{display:none}
#selbar.phrase-mode{position:fixed;left:50%;top:auto;
  bottom:calc(12px + env(safe-area-inset-bottom));transform:translateX(-50%);
  width:min(calc(100vw - 24px),520px);flex-wrap:wrap;justify-content:center;z-index:40}
#selbar.phrase-mode #sel-add,#selbar.phrase-mode #sel-phrase{display:none}
#selbar.phrase-mode #phrase-hint,#selbar.phrase-mode #phrase-cancel{display:inline-flex}
#selbar.phrase-ready #phrase-hint{display:none}
#selbar.phrase-ready #phrase-preview,#selbar.phrase-ready #phrase-add{display:inline-flex}
#phrase-preview{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
```

- [ ] **Step 3: Run `python -m unittest tests.test_interaction_template -v`**

Expected: markup/style assertions pass; helper assertions remain failing.

- [ ] **Step 4: Commit the toolbar shell**

```bash
git add template.html
git commit -m "feat: add mobile phrase selection toolbar"
```

### Task 3: Implement phrase range selection

**Files:**
- Modify: `template.html`
- Test: `tests/test_interaction_template.py`

- [ ] **Step 1: Add state and normalization helpers beside `selText`**

```javascript
let phraseStart=null, phraseEnd=null, phraseTokens=[];
function cleanPhraseEdge(text){
  return (text||'').trim().replace(/^[^A-Za-z]+|[^A-Za-z]+$/g,'');
}
function phraseFromTokens(tokens){
  return cleanPhraseEdge(tokens.map(t=>cleanPhraseEdge(t.dataset.w||t.textContent))
    .filter(Boolean).join(' '));
}
function clearPhraseHighlight(){
  phraseTokens.forEach(t=>t.classList.remove('phrase-selected')); phraseTokens=[];
}
```

- [ ] **Step 2: Add entry, selection, and cleanup functions**

```javascript
function exitPhraseMode(){
  clearPhraseHighlight(); phraseStart=null; phraseEnd=null; selText='';
  selbar.classList.remove('phrase-mode','phrase-ready');
  document.getElementById('phrase-preview').textContent='';
  document.getElementById('phrase-hint').textContent='';
  selbar.style.display='none';
}
function enterPhraseMode(){
  if(!phraseStart) return;
  clearPhraseHighlight(); phraseTokens=[phraseStart];
  phraseStart.classList.add('phrase-selected'); selText='';
  selbar.classList.add('phrase-mode'); selbar.classList.remove('phrase-ready');
  document.getElementById('phrase-hint').textContent='请选择短语最后一个词';
  selbar.style.display='flex';
}
function selectPhraseEnd(end){
  const start=phraseStart;
  if(!start||start.closest('.en')!==end.closest('.en')){
    toast('短语需在同一段内'); exitPhraseMode(); return;
  }
  const siblings=[...start.closest('.en').querySelectorAll('.tok')];
  const a=siblings.indexOf(start), b=siblings.indexOf(end);
  const selected=siblings.slice(Math.min(a,b),Math.max(a,b)+1);
  if(selected.length<2){ toast('请再选择一个词'); return; }
  if(selected.length>10){ toast('短语最多 10 个词'); return; }
  clearPhraseHighlight(); phraseTokens=selected; phraseEnd=end;
  phraseTokens.forEach(t=>t.classList.add('phrase-selected'));
  selText=phraseFromTokens(phraseTokens);
  document.getElementById('phrase-preview').textContent=selText;
  selbar.classList.add('phrase-ready');
}
```

- [ ] **Step 3: Wire events without native selection**

Set `phraseStart=tok` in the existing double-click handler. Add:

```javascript
artEl.addEventListener('click',e=>{
  if(!selbar.classList.contains('phrase-mode')) return;
  const tok=e.target.closest&&e.target.closest('.tok');
  if(!tok) return;
  e.preventDefault(); e.stopPropagation(); selectPhraseEnd(tok);
},true);
document.getElementById('sel-phrase').onclick=e=>{e.stopPropagation();enterPhraseMode();};
document.getElementById('phrase-add').onclick=e=>{
  e.stopPropagation(); if(selText){doAdd(selText);exitPhraseMode();}
};
document.getElementById('phrase-cancel').onclick=e=>{e.stopPropagation();exitPhraseMode();};
```

Make outside clicks call `exitPhraseMode()` when phrase mode is active. On scroll, hide only the ordinary word toolbar; keep the fixed phrase bar visible.

- [ ] **Step 4: Run interaction tests**

Run `python -m unittest tests.test_interaction_template -v`.

Expected: all tests pass.

- [ ] **Step 5: Commit the behavior**

```bash
git add template.html tests/test_interaction_template.py
git commit -m "feat: support phrase collection on mobile"
```

### Task 4: Rebuild and run the full verification suite

**Files:**
- Modify: `docs/2026-07-11.html`
- Modify: `docs/index.html`
- Modify: `tests/test_interaction_template.py`

- [ ] **Step 1: Rebuild the latest article**

```bash
TTS_API_URL='https://1300942703-hhwd575mtt.ap-guangzhou.tencentscf.com' python build.py articles/2026-07-11.json
```

Expected: `已生成 .../docs/2026-07-11.html`.

- [ ] **Step 2: Point the built-page test at the latest page**

```python
def test_latest_built_page_supports_word_and_phrase_collection(self):
    html = self.read("docs/2026-07-11.html")
    self.assert_double_click_vocab_only(html)
    self.assert_phrase_collection(html)
```

Replace the stale `docs/2026-07-03.html` test with this method.

- [ ] **Step 3: Run all tests**

Run `python -m unittest discover -v`.

Expected: all tests pass with no failures or errors.

- [ ] **Step 4: Check generated output**

Run `git diff --check`, `git diff --stat`, and `git status --short` separately.

Expected: only the template, interaction test, latest article, and mechanically regenerated index are changed.

- [ ] **Step 5: Commit generated output**

```bash
git add template.html tests/test_interaction_template.py docs/2026-07-11.html docs/index.html
git commit -m "build: publish mobile phrase collection"
```

### Task 5: Mobile smoke test and GitHub publication

**Files:**
- No source changes expected

- [ ] **Step 1: Serve the generated site locally**

Run `python -m http.server 8000 --directory docs`.

Expected: `http://localhost:8000/2026-07-11.html` responds.

- [ ] **Step 2: Verify the mobile flow in a narrow viewport**

Verify: ordinary double-click word toolbar; `a` to `of` previews `a cup of`; reverse selection produces the same phrase; cross-paragraph click cancels; cancel clears all highlights; native long-press selection remains available outside phrase mode.

- [ ] **Step 3: Push the verified commits**

Run `git status --short`, `git log -5 --oneline`, then `git push origin main`.

Expected: clean tree and a successful push to `origin/main`.

- [ ] **Step 4: Verify GitHub Pages**

Open `https://fanghongquan.github.io/english-daily/2026-07-11.html` after deployment and repeat the `a cup of` preview flow. Do not submit the smoke-test phrase to the third-party vocabulary service.
