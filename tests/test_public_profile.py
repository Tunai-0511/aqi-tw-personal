import unittest
from datetime import datetime

from backend.main import app
from backend.personalize import UserProfile, persona_dict, profile_block
from backend.pipeline import now_tpe_iso
from backend.schemas import ChatRequest, ProfileIn
from pydantic import ValidationError


class PublicProfileTests(unittest.TestCase):
    def test_non_sensitive_preferences_enable_personalization(self):
        profile = UserProfile.from_dict({
            "preferences_enabled": True,
            "sensitivity": "sensitive",
            "activity": "run",
            "threshold": 80,
            "city": "taipei",
        })

        self.assertTrue(profile.is_filled)
        self.assertFalse(profile.has_health_profile)
        block = profile_block(profile)
        self.assertIn("較敏感", block)
        self.assertIn("跑步", block)
        self.assertIn("不得推測", block)

    def test_public_persona_does_not_export_empty_health_fields(self):
        profile = UserProfile.from_dict({
            "preferences_enabled": True,
            "sensitivity": "general",
            "activity": "commute",
        })

        exported = persona_dict(profile)
        self.assertEqual(exported["activity"], "通勤")
        self.assertNotIn("med_history", exported)
        self.assertNotIn("diagnoses", exported)
        self.assertNotIn("age", exported)

    def test_empty_legacy_profile_stays_unfilled(self):
        self.assertFalse(UserProfile.from_dict(None).is_filled)

    def test_generated_timestamp_has_taipei_offset(self):
        generated = now_tpe_iso()
        parsed = datetime.fromisoformat(generated)
        self.assertEqual(parsed.utcoffset().total_seconds(), 8 * 60 * 60)

    def test_unsafe_public_diary_routes_are_not_exposed(self):
        paths = {route.path for route in app.routes}
        self.assertNotIn("/api/diary", paths)

    def test_public_request_fields_are_bounded(self):
        with self.assertRaises(ValidationError):
            ProfileIn(sensitivity="unknown")
        with self.assertRaises(ValidationError):
            ChatRequest(message="")


if __name__ == "__main__":
    unittest.main()
