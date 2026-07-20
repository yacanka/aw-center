"""Resource-oriented throttles for Outlook message processing."""

from django.conf import settings
from rest_framework.throttling import UserRateThrottle


class OutlookParseThrottle(UserRateThrottle):
    """Bound cache-producing message inspection per authenticated user."""

    scope = "outlook_parse"

    def get_rate(self):
        """Read the environment-backed rate without global DRF throttle state."""

        return settings.OUTLOOK_PARSE_RATE
