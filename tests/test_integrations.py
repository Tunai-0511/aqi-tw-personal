import unittest

from backend.config import settings
from backend.hermes_control import profile_name, provision_profile
from backend.integration_auth import current_user
from backend.integration_store import IntegrationStore
from backend.integrations import _make_state, _read_state, integration_config


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.original_dev = settings.integration_dev_mode
        self.original_secret = settings.integration_state_secret
        self.original_mode = settings.hermes_provision_mode
        settings.integration_dev_mode = True
        settings.integration_state_secret = "unit-test-state-secret-at-least-32-bytes"
        settings.hermes_provision_mode = "disabled"

    def tearDown(self):
        settings.integration_dev_mode = self.original_dev
        settings.integration_state_secret = self.original_secret
        settings.hermes_provision_mode = self.original_mode

    def test_oauth_state_round_trip(self):
        state = _make_state("demo-user")
        self.assertEqual(_read_state(state), "demo-user")

    def test_profile_name_is_safe_and_deterministic(self):
        first = profile_name("user/../../danger")
        self.assertEqual(first, profile_name("user/../../danger"))
        self.assertRegex(first, r"^aqi-[a-f0-9]{16}$")

    def test_disabled_provisioning_is_non_destructive(self):
        result = provision_profile("demo-user")
        self.assertEqual(result.status, "connected")
        self.assertIn("尚未啟用", result.detail)

    def test_dev_store_keeps_users_separate(self):
        store = IntegrationStore()
        store.upsert_integration("alice", "discord", platform_user_id="discord-a")
        store.upsert_integration("bob", "discord", platform_user_id="discord-b")
        self.assertEqual(len(store.list_integrations("alice")), 1)
        self.assertEqual(store.list_integrations("bob")[0]["user_id"], "bob")

    def test_public_config_never_returns_service_role(self):
        payload = integration_config()
        self.assertNotIn("supabase_service_role_key", payload)
        self.assertNotIn("discord_client_secret", payload)

    def test_demo_auth_sanitizes_header(self):
        user = current_user(authorization=None, x_demo_user="../tester!? ")
        self.assertEqual(user.id, "demo-tester")


if __name__ == "__main__":
    unittest.main()
