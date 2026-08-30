from django.utils.crypto import salted_hmac
from rest_framework.throttling import SimpleRateThrottle


class _ClientAddressThrottle(SimpleRateThrottle):
    """Bound an unauthenticated endpoint by DRF's trusted-proxy identity."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class _SensitiveValueThrottle(SimpleRateThrottle):
    """Throttle a submitted identifier without exposing it in the cache key."""

    field_names = ()
    casefold_value = True

    def get_cache_key(self, request, view):
        values = []
        request_data = getattr(request, "data", None)
        if request_data is None:
            request_data = getattr(request, "POST", {})
        for field_name in self.field_names:
            value = request_data.get(field_name, "")
            normalized = str(value).strip()[:512]
            if self.casefold_value:
                normalized = normalized.casefold()
            values.append(normalized)
        submitted_value = "\0".join(values)
        if not submitted_value.strip("\0"):
            return None
        digest = salted_hmac(
            f"awcenter.throttle.{self.scope}",
            submitted_value,
        ).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class LoginAddressThrottle(_ClientAddressThrottle):
    scope = "session_login_address"
    rate = "30/minute"


class LoginAccountThrottle(_SensitiveValueThrottle):
    scope = "session_login_account"
    rate = "10/minute"
    field_names = ("username",)


class AdminLoginAddressThrottle(_ClientAddressThrottle):
    scope = "admin_login_address"
    rate = "10/minute"


class PasswordResetAddressThrottle(_ClientAddressThrottle):
    scope = "password_reset_address"
    rate = "10/hour"


class PasswordResetAccountThrottle(_SensitiveValueThrottle):
    scope = "password_reset_account"
    rate = "20/hour"
    field_names = ("email",)


class PasswordResetConfirmAddressThrottle(_ClientAddressThrottle):
    scope = "password_reset_confirm_address"
    rate = "20/hour"


class PasswordResetCapabilityThrottle(_SensitiveValueThrottle):
    scope = "password_reset_capability"
    rate = "8/hour"
    field_names = ("uid", "token")
    casefold_value = False


class InvitationRateThrottle(_ClientAddressThrottle):
    """Rate-limit invitation probes by client address regardless of auth state."""

    scope = "invitation"
    rate = "60/hour"

class InvitationAcceptanceThrottle(InvitationRateThrottle):
    """Apply a stricter rate to account-creation attempts."""

    scope = "invitation_accept"
    rate = "20/hour"
