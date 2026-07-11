# Remove Vocabulary Section Design

## Scope

Remove the generated article's standalone “重点词汇” section, search field, count, vocabulary rows, speech buttons, and Maimemo buttons.

Keep inline keyword emphasis and IPA annotations in the English paragraphs. Keep paragraph/full-article narration, native mobile text selection, double-click word handling, and all reading-progress and quiz features.

## Verification

Add a regression contract asserting the template and rebuilt page contain no vocabulary section or vocabulary-list JavaScript. Run the complete suite, rebuild the latest page, verify generated JavaScript syntax, merge, and publish through GitHub Pages.
