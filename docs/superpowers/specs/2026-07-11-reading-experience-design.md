# Mobile Reading Experience Design

## Goal

Improve daily mobile reading with a compact hybrid toolbar, durable local reading progress, paragraph narration, an automatically generated vocabulary list, and scored comprehension practice.

## Constraints

- Keep each generated article self-contained; do not add a frontend build system or framework.
- Preserve desktop behavior and existing article JSON compatibility.
- Store progress only on the current device through `localStorage`.
- Keep browser speech available when authenticated cloud speech is unavailable.
- Maintain keyboard and screen-reader accessibility.

## Mobile Layout

The selected layout is the hybrid floating option.

- A three-pixel progress bar stays at the top of the viewport and reflects document reading progress.
- Translation and IPA controls remain in the opening toolbar because they describe persistent display state.
- Below the mobile breakpoint, speech rate, voice, theme, and access-code controls move into a collapsible “更多” panel.
- After the opening toolbar scrolls away, a compact floating control appears above the safe-area inset with “朗读/暂停” and “更多”. It hides near the page top and while the expanded panel is open.
- Desktop keeps the full inline toolbar.

## Reading Progress

Progress uses a versioned key such as `englishDaily:progress:<article-date>`. Stored data contains the scroll ratio, last paragraph index, completion flag, quiz score, quiz total, and update timestamp.

Scroll updates are throttled. A page is complete at 92% document progress or after the final quiz question is answered. When a returning reader has meaningful saved progress, a small non-blocking banner offers “继续阅读” and “从头开始”; the page never jumps without confirmation.

The archive reads these local records and marks completed articles. This enhancement is progressive: missing or malformed storage is ignored.

## Narration

The existing speech engine becomes a single stateful controller for full-article and paragraph playback.

- Every paragraph receives an accessible “朗读本段” button.
- The active paragraph gets a visible speaking state and `aria-current` indicator.
- Starting a new paragraph cancels current playback.
- The mobile floating button starts or stops the current paragraph; when none is active, it starts at the paragraph nearest the viewport center.
- Cloud request failure falls back to browser speech without losing the active visual state.
- Controls expose `aria-pressed` and meaningful labels.

## Vocabulary List

The page derives vocabulary from sanitized `span.kw` elements after rendering. Words are normalized case-insensitively and de-duplicated while preserving first appearance.

Each row shows word, IPA, Chinese definition, occurrence count, speech action, and Maimemo action. The list supports a simple client-side filter and shows the total unique count. It uses the existing protected request helper for cloud speech and Maimemo.

No new model schema field is required, so historical articles gain the feature when rebuilt.

## Quiz Scoring

The quiz tracks one answer per question. After all questions are answered, it displays score, percentage, incorrect question numbers, “只看错题”, and “重新作答”. Reset clears visual and stored quiz state for the article.

Answered state and score are stored in the article progress record. The initial implementation restores only the final summary, not partially selected answers, to keep the state contract small and predictable.

## Accessibility and Responsive Behavior

- English content uses `lang="en-US"`; Chinese translations use `lang="zh-CN"`.
- Toggle buttons maintain `aria-pressed`.
- Range and select controls have explicit labels.
- All interactive elements receive `:focus-visible` styles.
- Floating controls respect `env(safe-area-inset-bottom)` and never cover the final content because the mobile page adds matching bottom padding.
- Motion is reduced under `prefers-reduced-motion`.

## Testing

Tests remain standard-library `unittest` contracts plus generated-page JavaScript syntax verification. They cover:

- required mobile toolbar, safe-area, and progress markup;
- local progress key and continue/reset behavior;
- one paragraph speech control per paragraph and active-state contracts;
- vocabulary extraction, de-duplication, filter, speech, and Maimemo actions;
- quiz score, incorrect-only filtering, reset, and persistence markers;
- language, labels, ARIA state, and focus-visible styles;
- successful real build of the latest article.

## Release

Implement in an isolated feature worktree, keep commits scoped by feature, run the complete suite and generated JavaScript syntax check, merge to `main`, push GitHub, and wait for Pages deployment. SCF does not require another code change for these five features.
