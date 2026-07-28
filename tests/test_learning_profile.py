import unittest
import urllib.error
from unittest.mock import call, patch

from scf import index as scf


NOW = "2026-07-28T00:00:00Z"


def feedback(article_date="2026-07-28", **overrides):
    payload = {
        "article_date": article_date,
        "difficulty": "balanced",
        "completed": True,
        "quiz_first_score": 3,
        "quiz_total": 4,
        "word_action_count": 6,
        "phrase_action_count": 1,
    }
    payload.update(overrides)
    return payload


class FeedbackNormalizationTest(unittest.TestCase):
    def test_normalizes_valid_feedback(self):
        event = scf._normalize_feedback(feedback(), NOW)
        self.assertEqual("2026-07-28", event["article_date"])
        self.assertEqual("balanced", event["difficulty"])
        self.assertEqual(3, event["quiz_first_score"])
        self.assertEqual(NOW, event["updated_at"])

    def test_rejects_invalid_scalar_values(self):
        invalid_payloads = (
            feedback(article_date="28-07-2026"),
            feedback(difficulty="medium"),
            feedback(completed=1),
            feedback(quiz_first_score=5, quiz_total=4),
            feedback(quiz_first_score=True),
            feedback(word_action_count=-1),
            feedback(phrase_action_count=101),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                scf._normalize_feedback(payload, NOW)

    def test_merge_preserves_first_score_and_monotonic_counts(self):
        original = scf._normalize_feedback(feedback(
            difficulty="easy", completed=True, quiz_first_score=2,
            word_action_count=7, phrase_action_count=2), NOW)
        merged = scf._merge_feedback(original, feedback(
            difficulty="hard", completed=False, quiz_first_score=4,
            word_action_count=3, phrase_action_count=1),
            "2026-07-28T01:00:00Z")
        self.assertEqual("hard", merged["difficulty"])
        self.assertTrue(merged["completed"])
        self.assertEqual(2, merged["quiz_first_score"])
        self.assertEqual(7, merged["word_action_count"])
        self.assertEqual(2, merged["phrase_action_count"])

    def test_null_difficulty_does_not_erase_subjective_feedback(self):
        original = scf._normalize_feedback(feedback(difficulty="easy"), NOW)
        merged = scf._merge_feedback(
            original, feedback(difficulty=None), "2026-07-28T01:00:00Z")
        self.assertEqual("easy", merged["difficulty"])


class LearningSignalTest(unittest.TestCase):
    def test_easy_article_produces_positive_signal(self):
        event = scf._normalize_feedback(feedback(
            difficulty="easy", quiz_first_score=4,
            word_action_count=2, phrase_action_count=0), NOW)
        self.assertGreater(scf._event_signal(event), 0)

    def test_hard_article_produces_negative_signal(self):
        event = scf._normalize_feedback(feedback(
            difficulty="hard", quiz_first_score=1,
            word_action_count=10, phrase_action_count=2), NOW)
        self.assertLess(scf._event_signal(event), 0)

    def test_objective_only_signal_keeps_subjective_weight_unassigned(self):
        objective_only = scf._normalize_feedback(feedback(
            difficulty=None, quiz_first_score=4,
            word_action_count=1, phrase_action_count=0), NOW)
        subjective = scf._normalize_feedback(feedback(
            difficulty="easy", quiz_first_score=4,
            word_action_count=1, phrase_action_count=0), NOW)
        self.assertGreater(scf._event_signal(objective_only), 0)
        self.assertLess(scf._event_signal(objective_only),
                        scf._event_signal(subjective))


class LearningProfileTest(unittest.TestCase):
    def test_default_profile_is_balanced_and_independent(self):
        first = scf._default_profile()
        second = scf._default_profile()
        first["recent"].append({"article_date": "changed"})
        self.assertEqual([], second["recent"])
        self.assertEqual(0, second["observation_count"])
        self.assertEqual(900, second["target_words"])

    def test_first_three_distinct_articles_use_calibration_step(self):
        profile = scf._default_profile()
        for day in range(1, 4):
            profile = scf._update_profile(
                profile,
                scf._normalize_feedback(feedback(
                    article_date=f"2026-07-0{day}", difficulty="easy",
                    quiz_first_score=4, word_action_count=1,
                    phrase_action_count=0), NOW),
                NOW)
        self.assertEqual(3, profile["observation_count"])
        self.assertTrue(all(item["step"] == 1.0 for item in profile["recent"]))

        profile = scf._update_profile(
            profile,
            scf._normalize_feedback(feedback(
                article_date="2026-07-04", difficulty="easy",
                quiz_first_score=4, word_action_count=1,
                phrase_action_count=0), NOW),
            NOW)
        self.assertEqual(2.0, profile["recent"][-1]["step"])

    def test_same_date_recomputes_without_double_counting(self):
        profile = scf._default_profile()
        easy = scf._normalize_feedback(feedback(difficulty="easy"), NOW)
        first = scf._update_profile(profile, easy, NOW)
        hard = scf._normalize_feedback(feedback(difficulty="hard"), NOW)
        revised = scf._update_profile(first, hard, NOW)
        expected = scf._update_profile(scf._default_profile(), hard, NOW)
        self.assertEqual(1, revised["observation_count"])
        self.assertAlmostEqual(expected["ability_score"],
                               revised["ability_score"])

    def test_recent_window_rolls_oldest_signal_into_base(self):
        profile = scf._default_profile()
        for day in range(1, 9):
            event = scf._normalize_feedback(feedback(
                article_date=f"2026-07-{day:02d}", difficulty="easy",
                quiz_first_score=4, word_action_count=1,
                phrase_action_count=0), NOW)
            profile = scf._update_profile(profile, event, NOW)
        self.assertEqual(8, profile["observation_count"])
        self.assertEqual(7, len(profile["recent"]))
        self.assertEqual("2026-07-02", profile["recent"][0]["article_date"])
        self.assertGreater(profile["base_score"], 50.0)

    def test_rebuild_is_idempotent_and_profile_stays_bounded(self):
        events = [
            scf._normalize_feedback(feedback(
                article_date=(
                    __import__("datetime").date(2025, 1, 1)
                    + __import__("datetime").timedelta(days=day)
                ).isoformat(),
                difficulty="easy", quiz_first_score=4,
                word_action_count=1, phrase_action_count=0), NOW)
            for day in range(400)
        ]
        profile = scf._profile_from_events(events + events, NOW)
        self.assertEqual(400, profile["observation_count"])
        self.assertEqual(7, len(profile["recent"]))
        self.assertNotIn("observed_dates", profile)

    def test_rebuild_revises_rolled_out_date_without_double_counting(self):
        events = [
            scf._normalize_feedback(feedback(
                article_date=f"2026-07-{day:02d}", difficulty="easy",
                quiz_first_score=4, word_action_count=1,
                phrase_action_count=0), NOW)
            for day in range(1, 9)
        ]
        original = scf._profile_from_events(events, NOW)
        revised = scf._normalize_feedback(feedback(
            article_date="2026-07-01", difficulty="hard",
            quiz_first_score=1, word_action_count=10,
            phrase_action_count=2), "2026-07-28T01:00:00Z")
        changed = scf._profile_from_events(events + [revised], NOW)
        replayed = scf._profile_from_events(
            events + [revised, revised], NOW)
        self.assertEqual(8, changed["observation_count"])
        self.assertLess(changed["ability_score"], original["ability_score"])
        self.assertEqual(changed["ability_score"], replayed["ability_score"])

    def test_rebuild_orders_second_and_microsecond_timestamps_correctly(self):
        old = scf._normalize_feedback(
            feedback(difficulty="hard"), "2026-07-28T00:00:00Z")
        new = scf._normalize_feedback(
            feedback(difficulty="easy"), "2026-07-28T00:00:00.500000Z")
        rebuilt = scf._profile_from_events([new, old], NOW)
        self.assertGreater(rebuilt["recent"][0]["signal"], 0)

    def test_targets_remain_in_product_bounds(self):
        profile = scf._default_profile()
        for day in range(1, 20):
            event = scf._normalize_feedback(feedback(
                article_date=f"2026-08-{day:02d}", difficulty="easy",
                quiz_first_score=4, word_action_count=0,
                phrase_action_count=0), NOW)
            profile = scf._update_profile(profile, event, NOW)
        self.assertLessEqual(profile["ability_score"], 80)
        self.assertLessEqual(profile["target_words"], 1100)
        self.assertLessEqual(profile["target_new_words"], 8)
        self.assertLessEqual(profile["sentence_level"], 5)


class LearningProfilePersistenceTest(unittest.TestCase):
    def test_cos_json_get_returns_none_on_missing_object(self):
        missing = urllib.error.HTTPError(
            "https://cos.test/object", 404, "missing", {}, None)
        with patch.object(scf, "_cos_req", side_effect=missing):
            self.assertIsNone(
                scf._cos_json_get("missing.json", "sid", "skey", "token"))

    def test_observation_key_is_self_contained_and_immutable(self):
        first = scf._normalize_feedback(feedback(difficulty="easy"), NOW)
        later = dict(first, updated_at="2026-07-28T01:00:00Z")
        changed = dict(first, difficulty="hard")
        self.assertEqual(
            first, scf._observation_from_key(scf._observation_key(first)))
        self.assertNotEqual(
            scf._observation_key(first), scf._observation_key(later))
        self.assertNotEqual(
            scf._observation_key(first), scf._observation_key(changed))

    def test_cos_auth_signs_list_query_names(self):
        auth = scf._cos_auth(
            "GET", "/", "sid", "skey",
            query={"prefix": "learning-profile/", "max-keys": "1000"})
        self.assertIn("q-url-param-list=max-keys;prefix", auth)

    def test_cos_list_keys_handles_namespace_and_pagination(self):
        first = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://www.qcloud.com/document/product/436/7751">
  <IsTruncated>true</IsTruncated>
  <NextMarker>learning-profile/observations/next.json</NextMarker>
  <Contents><Key>learning-profile/observations/one.json</Key></Contents>
</ListBucketResult>"""
        second = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://www.qcloud.com/document/product/436/7751">
  <IsTruncated>false</IsTruncated>
  <Contents><Key>learning-profile/observations/two.json</Key></Contents>
</ListBucketResult>"""
        with patch.object(scf, "_cos_req",
                          side_effect=[first, second]) as request:
            keys = scf._cos_list_keys(
                "learning-profile/observations/", "sid", "skey", "token")
        self.assertEqual([
            "learning-profile/observations/one.json",
            "learning-profile/observations/two.json",
        ], keys)
        self.assertEqual(
            "learning-profile/observations/next.json",
            request.call_args_list[1].kwargs["query"]["marker"])

    def test_feedback_put_appends_observation_then_rebuilds_cache(self):
        incoming = feedback(difficulty="easy")
        prior = scf._normalize_feedback(
            feedback(article_date="2026-07-27"), NOW)
        with patch.object(scf, "_load_feedback_events",
                          return_value=[prior]), \
                patch.object(scf, "_cos_json_get", return_value=None), \
                patch.object(scf, "_cos_json_put") as put:
            result = scf.do_feedback_put(
                "sid", "skey", "token", incoming, now=NOW)
        self.assertTrue(result["ok"])
        self.assertEqual("harder", result["profile"]["trend"])
        event = scf._normalize_feedback(incoming, NOW)
        profile = put.call_args_list[1].args[1]
        self.assertEqual(2, profile["observation_count"])
        self.assertEqual(
            call(scf._observation_key(event), event,
                 "sid", "skey", "token"),
            put.call_args_list[0])
        self.assertEqual(
            call(scf.PROFILE_KEY, profile, "sid", "skey", "token"),
            put.call_args_list[1])

    def test_profile_get_returns_only_derived_fields(self):
        stored_event = scf._normalize_feedback(feedback(), NOW)
        with patch.object(scf, "_load_feedback_events",
                          return_value=[stored_event]), \
                patch.object(scf, "_cos_json_get", return_value=None):
            result = scf.do_profile_get("sid", "skey", "token")
        self.assertNotIn("recent", result["profile"])
        self.assertEqual(1, result["profile"]["observation_count"])
        self.assertEqual("85%-90%",
                         result["profile"]["target_comprehension"])

    def test_concurrent_same_date_observations_merge_without_data_loss(self):
        incoming = feedback(
            difficulty="hard", completed=False, quiz_first_score=4,
            word_action_count=2, phrase_action_count=1)
        concurrent = scf._normalize_feedback(feedback(
            difficulty="easy", completed=True, quiz_first_score=2,
            word_action_count=8, phrase_action_count=3), NOW)
        with patch.object(scf, "_load_feedback_events",
                          return_value=[concurrent]), \
                patch.object(scf, "_cos_json_get", return_value=None), \
                patch.object(scf, "_cos_json_put") as put:
            result = scf.do_feedback_put(
                "sid", "skey", "token", incoming, now=NOW)
        self.assertEqual(1, result["profile"]["observation_count"])
        rebuilt = put.call_args_list[1].args[1]
        expected_event = scf._profile_from_events([
            concurrent, scf._normalize_feedback(incoming, NOW)], NOW)
        self.assertEqual(expected_event["ability_score"],
                         rebuilt["ability_score"])

    def test_profile_get_falls_back_to_legacy_cache_without_events(self):
        legacy = scf._default_profile()
        legacy["observation_count"] = 8
        with patch.object(scf, "_load_feedback_events", return_value=[]), \
                patch.object(scf, "_cos_json_get", return_value=legacy):
            result = scf.do_profile_get("sid", "skey", "token")
        self.assertEqual(8, result["profile"]["observation_count"])

    def test_profile_get_uses_cache_when_list_snapshot_is_partial(self):
        cached = scf._default_profile()
        cached.update({
            "observation_count": 8,
            "ability_score": 63.0,
            "source_event_count": 8,
            "source_latest_at": "2026-07-28T00:00:00Z",
        })
        partial = scf._normalize_feedback(
            feedback(article_date="2026-07-21"), NOW)
        with patch.object(scf, "_load_feedback_events",
                          return_value=[partial]), \
                patch.object(scf, "_cos_json_get", return_value=cached):
            result = scf.do_profile_get("sid", "skey", "token")
        self.assertEqual(8, result["profile"]["observation_count"])
        self.assertEqual(63.0, result["profile"]["ability_score"])

    def test_feedback_put_does_not_overwrite_fresher_cache_with_partial_list(self):
        cached = scf._default_profile()
        cached.update({
            "observation_count": 8,
            "ability_score": 63.0,
            "source_event_count": 8,
            "source_latest_at": "2026-07-27T00:00:00Z",
        })
        partial = scf._normalize_feedback(
            feedback(article_date="2026-07-27"), NOW)
        with patch.object(scf, "_load_feedback_events",
                          return_value=[partial]), \
                patch.object(scf, "_cos_json_get", return_value=cached), \
                patch.object(scf, "_cos_json_put") as put:
            result = scf.do_feedback_put(
                "sid", "skey", "token",
                feedback(article_date="2026-07-28"), now=NOW)
        self.assertEqual(63.0, result["profile"]["ability_score"])
        self.assertEqual(1, put.call_count)


if __name__ == "__main__":
    unittest.main()
