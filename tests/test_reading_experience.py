import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadingExperienceContractTest(unittest.TestCase):
    def template(self):
        return (ROOT / "template.html").read_text(encoding="utf-8")

    def test_mobile_hybrid_toolbar_and_accessibility_contract(self):
        html = self.template()
        for marker in (
            'id="read-progress"', 'role="progressbar"', 'id="mobile-float"',
            'id="mobile-play"', 'id="mobile-more"', 'id="mobile-panel"',
            'env(safe-area-inset-bottom)', '@media (max-width:640px)',
            ':focus-visible', 'prefers-reduced-motion', 'for="rate"',
            'for="voice"', "setAttribute('aria-pressed'", "lang='en-US'",
            "lang='zh-CN'",
        ):
            self.assertIn(marker, html)

    def test_local_reading_progress_and_resume_contract(self):
        html = self.template()
        for marker in (
            "englishDaily:progress:", "function loadProgress", "function saveProgress",
            "requestAnimationFrame", 'id="continue-reading"', "继续阅读", "从头开始",
            "ratio>=.92", "lastParagraph", "aria-valuenow", "scrollTo",
        ):
            self.assertIn(marker, html)

    def test_paragraph_narration_contract(self):
        html = self.template()
        for marker in (
            "朗读本段", "data-paragraph", "activeParagraph", "function setSpeakingState",
            "aria-current", "nearestParagraph()", "startParagraph", "mobile-play",
        ):
            self.assertIn(marker, html)

    def test_standalone_vocabulary_list_is_removed(self):
        html = self.template()
        for marker in (
            'id="vocab-sec"', 'id="vocab-filter"', "function collectVocabulary",
            "vocab-play", "vocab-add",
        ):
            self.assertNotIn(marker, html)
        self.assertIn('.en .kw', html)
        self.assertIn('function applyIpa', html)

    def test_quiz_scoring_review_and_persistence_contract(self):
        html = self.template()
        for marker in (
            'id="quiz-summary"', "quizScore", "answeredCount", "incorrectQuestions",
            "只看错题", "重新作答", "function updateQuizSummary",
            "quizScore:quizScore", "saveProgress",
        ):
            self.assertIn(marker, html)

    def test_mobile_difficulty_feedback_and_pending_queue_contract(self):
        html = self.template()
        for marker in (
            'id="difficulty-feedback"',
            'data-value="easy"',
            'data-value="balanced"',
            'data-value="hard"',
            'aria-pressed="false"',
            'id="feedback-status" aria-live="polite"',
            "min-height:48px",
            "englishDaily:feedback:pending",
            "quizFirstScore",
            "wordActionCount",
            "phraseActionCount",
            "learningActionKeys",
            "function syncLearningFeedback",
            "word_action_count",
            "phrase_action_count",
        ):
            self.assertIn(marker, html)

    def test_feedback_queue_drains_all_dates_without_synthesizing_retries(self):
        html = self.template()
        for marker in (
            "function hasMeaningfulFeedback",
            "function queueCurrentLearningFeedback",
            "Object.keys(queue).sort()",
            "feedbackSyncPromise",
            "JSON.stringify(latest)===JSON.stringify(payload)",
            "if(!dates.length)return true",
        ):
            self.assertIn(marker, html)
        sync = html[
            html.index("async function syncLearningFeedback"):
            html.index("function scheduleLearningFeedbackSync")]
        self.assertNotIn("learningFeedbackPayload();", sync)

    def test_quiz_reset_preserves_first_diagnostic_score(self):
        html = self.template()
        self.assertIn("quizFirstScore==null?quizScore", html)
        restart = html[
            html.index("document.getElementById('restart-reading').onclick"):
            html.index("/* 理解自测：")]
        self.assertNotIn("quizTotal:0", restart)
        reset = html[html.index("document.getElementById('quiz-reset').onclick"):
                     html.index("/* ========== 工具条 ========== */")]
        self.assertNotIn("quizFirstScore:null", reset)

    def test_archive_marks_completed_articles_from_local_progress(self):
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        for marker in ('data-date="{date}"', "englishDaily:progress:", "completed", "已读"):
            self.assertIn(marker, build)


if __name__ == "__main__":
    unittest.main()
