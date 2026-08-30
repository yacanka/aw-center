"""AW Center composition root and canonical first-production API surface."""

from django.contrib import admin
from django.urls import include, path

from attention.api import action_center, action_center_decision
from users.session_api import SessionView

from .views import health_live, health_ready, redirect_to_app


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("api/session/", SessionView.as_view(), name="session"),
    path("api/projects/", include("projects.urls")),
    path(
        "api/projects/<slug:project_slug>/organization/",
        include("orgs.urls"),
    ),
    path(
        "api/projects/<slug:project_slug>/compliance-documents/",
        include("compliance.urls"),
    ),
    path("api/attention/", action_center, name="attention"),
    path("api/attention/decisions/", action_center_decision, name="attention-decision"),
    path("api/integrations/", include("integrations.urls")),
    path("api/integrations/doors/", include("integrations.doors.urls")),
    path("api/integrations/teamcenter/", include("integrations.teamcenter.urls")),
    path("api/integrations/docproof/", include("integrations.docproof_urls")),
    path("api/dcc/", include("dcc.urls")),
    path("api/users/", include("users.urls")),
    path("api/jobs/", include("jobs.urls")),
    path("api/workflows/", include("automations.workflow_urls")),
    path("internal/bridge/v1/", include("automations.bridge_urls")),
    path("api/releases/", include("releases.urls")),
    path("api/tools/ddf/", include("ddf.urls")),
    path("api/tools/excel/", include("excel.urls")),
    path("api/tools/word/", include("word.urls")),
    path("api/tools/pdf/", include("pdf.urls")),
    path("api/tools/outlook/", include("outlook.urls")),
    path("api/tools/presentations/", include("pptxgallery.urls")),
    path("api/tools/media/", include("media_tools.urls")),
    path("app/", include("awcenter.spa_urls")),
    path("", redirect_to_app),
]
