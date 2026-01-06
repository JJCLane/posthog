from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

import requests

from posthog.services.esp_suppression import SUPPRESSION_CACHE_TTL, ESPSuppressionService


class TestESPSuppressionService(SimpleTestCase):
    def setUp(self):
        self.service = ESPSuppressionService()

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    def test_cache_hit_returns_cached_value_without_api_call(self, mock_cache):
        mock_cache.get.return_value = True

        with patch("posthog.services.esp_suppression.requests.get") as mock_get:
            result = self.service.check_email_suppressed("test@example.com")

            mock_get.assert_not_called()
            self.assertTrue(result.is_suppressed)
            self.assertTrue(result.from_cache)

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    @patch("posthog.services.esp_suppression.requests.get")
    def test_cache_miss_triggers_api_call_and_caches_result(self, mock_get, mock_cache):
        mock_cache.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"email": "test@example.com", "suppressed": True}]
        mock_get.return_value = mock_response

        result = self.service.check_email_suppressed("test@example.com")

        mock_get.assert_called_once()
        mock_cache.set.assert_called_once()
        self.assertTrue(result.is_suppressed)
        self.assertFalse(result.from_cache)

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    @patch("posthog.services.esp_suppression.requests.get")
    def test_api_timeout_fails_closed(self, mock_get, mock_cache):
        mock_cache.get.return_value = None
        mock_get.side_effect = requests.Timeout()

        result = self.service.check_email_suppressed("test@example.com")

        self.assertTrue(result.is_suppressed)
        self.assertFalse(result.from_cache)
        self.assertEqual(result.reason, "api_error")

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    @patch("posthog.services.esp_suppression.requests.get")
    def test_api_error_fails_closed(self, mock_get, mock_cache):
        mock_cache.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        result = self.service.check_email_suppressed("test@example.com")

        self.assertTrue(result.is_suppressed)
        self.assertFalse(result.from_cache)
        self.assertEqual(result.reason, "api_error")

    @override_settings(CUSTOMER_IO_APP_API_KEY="")
    def test_feature_gating_when_customer_io_not_configured(self):
        result = self.service.check_email_suppressed("test@example.com")

        self.assertFalse(result.is_suppressed)
        self.assertFalse(result.from_cache)
        self.assertEqual(result.reason, "not_configured")

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    def test_email_hash_is_used_in_cache_key(self):
        cache_key_1 = self.service._get_cache_key("test@example.com")
        cache_key_2 = self.service._get_cache_key("TEST@EXAMPLE.COM")
        cache_key_3 = self.service._get_cache_key("other@example.com")

        self.assertTrue(cache_key_1.startswith("email_mfa_suppressed:"))
        self.assertEqual(cache_key_1, cache_key_2)
        self.assertNotEqual(cache_key_1, cache_key_3)
        self.assertNotIn("@", cache_key_1)

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    @patch("posthog.services.esp_suppression.requests.get")
    def test_404_response_means_not_suppressed(self, mock_get, mock_cache):
        mock_cache.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = self.service.check_email_suppressed("test@example.com")

        self.assertFalse(result.is_suppressed)
        self.assertFalse(result.from_cache)
        mock_cache.set.assert_called_once()

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    def test_empty_email_returns_not_suppressed(self):
        result = self.service.check_email_suppressed("")

        self.assertFalse(result.is_suppressed)
        self.assertEqual(result.reason, "empty_email")

    @override_settings(CUSTOMER_IO_APP_API_KEY="test-app-api-key")
    @patch("posthog.services.esp_suppression.cache")
    @patch("posthog.services.esp_suppression.requests.get")
    def test_cache_set_with_correct_ttl(self, mock_get, mock_cache):
        mock_cache.get.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        self.service.check_email_suppressed("test@example.com")

        call_args = mock_cache.set.call_args
        self.assertEqual(call_args[0][2], SUPPRESSION_CACHE_TTL)
