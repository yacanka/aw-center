from rest_framework.throttling import SimpleRateThrottle


class InvitationRateThrottle(SimpleRateThrottle):
    """Rate-limit invitation probes by client address regardless of auth state."""

    scope = "invitation"
    rate = "60/hour"

    def get_cache_key(self, request, view):
        """Return a bounded client key using DRF's trusted-proxy policy."""

        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class InvitationAcceptanceThrottle(InvitationRateThrottle):
    """Apply a stricter rate to account-creation attempts."""

    scope = "invitation_accept"
    rate = "20/hour"
