import math

from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.http import HttpResponse

from users.throttles import AdminLoginAddressThrottle


class AwCenterAdminSite(AdminSite):
    site_header = "AW Center administration"
    site_title = "AW Center"

    def login(self, request, extra_context=None):
        """Rate-limit only credential submissions to the operator login."""

        if request.method == "POST":
            throttle = AdminLoginAddressThrottle()
            if not throttle.allow_request(request, self):
                wait_seconds = max(math.ceil(throttle.wait() or 1), 1)
                return HttpResponse(
                    "Too many login attempts. Try again later.",
                    status=429,
                    headers={"Retry-After": str(wait_seconds)},
                    content_type="text/plain; charset=utf-8",
                )
        return super().login(request, extra_context=extra_context)


class AwCenterAdminConfig(AdminConfig):
    """Use the AW Center admin site and register production checks."""

    default_site = "awcenter.admin.AwCenterAdminSite"

    def ready(self):
        super().ready()
        from . import checks  # noqa: F401
