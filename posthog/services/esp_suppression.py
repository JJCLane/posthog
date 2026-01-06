import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache

import requests
import structlog

from posthog.settings.web import TWO_FACTOR_REMEMBER_COOKIE_AGE

logger = structlog.get_logger(__name__)

SUPPRESSION_CACHE_TTL = TWO_FACTOR_REMEMBER_COOKIE_AGE  # 30 days
API_TIMEOUT_SECONDS = 5


@dataclass
class SuppressionCheckResult:
    is_suppressed: bool
    from_cache: bool
    reason: Optional[str] = None


class ESPSuppressionService:
    def _get_cache_key(self, email: str) -> str:
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        return f"email_mfa_suppressed:{email_hash}"

    def _is_configured(self) -> bool:
        return bool(getattr(settings, "CUSTOMER_IO_APP_API_KEY", ""))

    def check_email_suppressed(self, email: str) -> SuppressionCheckResult:
        if not self._is_configured():
            return SuppressionCheckResult(is_suppressed=False, from_cache=False, reason="not_configured")

        if not email:
            return SuppressionCheckResult(is_suppressed=False, from_cache=False, reason="empty_email")

        cache_key = self._get_cache_key(email)
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            logger.info(
                "ESP suppression check cache hit",
                email_hash=hashlib.sha256(email.lower().encode()).hexdigest()[:8],
                cached_result=cached_result,
            )
            return SuppressionCheckResult(
                is_suppressed=cached_result, from_cache=True, reason="suppressed" if cached_result else None
            )

        try:
            api_key = getattr(settings, "CUSTOMER_IO_APP_API_KEY", "")
            api_url = getattr(settings, "CUSTOMER_IO_API_URL", "https://api-eu.customer.io")

            if not api_key:
                return SuppressionCheckResult(is_suppressed=False, from_cache=False, reason="no_api_key")

            response = requests.get(
                f"{api_url}/v1/esp/suppressions",
                params={"email": email},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=API_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                data = response.json()
                is_suppressed = self._parse_suppression_response(data)
                cache.set(cache_key, is_suppressed, SUPPRESSION_CACHE_TTL)
                logger.info(
                    "ESP suppression check API success",
                    email_hash=hashlib.sha256(email.lower().encode()).hexdigest()[:8],
                    is_suppressed=is_suppressed,
                )
                return SuppressionCheckResult(
                    is_suppressed=is_suppressed,
                    from_cache=False,
                    reason="suppressed" if is_suppressed else None,
                )
            elif response.status_code == 404:
                cache.set(cache_key, False, SUPPRESSION_CACHE_TTL)
                logger.info(
                    "ESP suppression check: email not on suppression list",
                    email_hash=hashlib.sha256(email.lower().encode()).hexdigest()[:8],
                )
                return SuppressionCheckResult(is_suppressed=False, from_cache=False, reason=None)
            else:
                logger.warning(
                    "ESP suppression check API error - failing closed",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else None,
                )
                return SuppressionCheckResult(is_suppressed=True, from_cache=False, reason="api_error")

        except requests.Timeout:
            logger.warning("ESP suppression check timeout - failing closed")
            return SuppressionCheckResult(is_suppressed=True, from_cache=False, reason="api_error")
        except requests.RequestException as e:
            logger.warning("ESP suppression check network error - failing closed", error=str(e))
            return SuppressionCheckResult(is_suppressed=True, from_cache=False, reason="api_error")
        except Exception as e:
            logger.exception("ESP suppression check unexpected error - failing closed", error=str(e))
            return SuppressionCheckResult(is_suppressed=True, from_cache=False, reason="api_error")

    def _parse_suppression_response(self, data: Any) -> bool:
        if not data:
            return False
        if isinstance(data, list):
            return len(data) > 0
        if isinstance(data, dict):
            return bool(data.get("suppressed", False)) or bool(data.get("suppressions", []))
        return False


esp_suppression_service = ESPSuppressionService()
