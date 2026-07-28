from projects.aesa.models import CompDoc
from projects.aesa.serializers import CompDocSerializer, HistorySerializer

from common.compdoc_import_views import upload_compdoc_factory
from common.compdoc_excel_export import excel_creator_factory
from common.compdoc_dashboard_views import compdoc_dashboard_view_factory
from common.compdoc_notification_policy_views import compdoc_notification_policy_view_factory
from common.compdoc_tracking_views import (
    compdoc_docproof_view_factory,
    compdoc_notification_draft_view_factory,
    compdoc_notification_view_factory,
    compdoc_tracking_view_factory,
)
from common.compdoc_lifecycle_views import (
    activity_view_factory, archive_view_factory, transition_view_factory, work_view_factory,
)
from common.compdoc_bulk_views import bulk_view_factory
from common.compdoc_review_views import (
    assignee_view_factory, review_decision_view_factory, review_view_factory,
)
from common.views import view_set_factory, view_set_obj_factory, history_view_set_factory, compdoc_fields_view_factory

from rest_framework.permissions import IsAuthenticated

CompDocView = view_set_factory(CompDoc, CompDocSerializer, [IsAuthenticated])
CompDocObjView = view_set_obj_factory(CompDoc, CompDocSerializer, [IsAuthenticated])

CompDocUpload = upload_compdoc_factory(CompDoc, CompDocSerializer, [IsAuthenticated])
ExcelCreator = excel_creator_factory(CompDoc, CompDocSerializer, [IsAuthenticated])

HistoryView = history_view_set_factory(CompDoc, HistorySerializer, [IsAuthenticated])
CompDocFields = compdoc_fields_view_factory(CompDoc, [IsAuthenticated])
CompDocDashboard = compdoc_dashboard_view_factory(CompDoc, [IsAuthenticated])
CompDocNotificationPolicy = compdoc_notification_policy_view_factory(CompDoc)
CompDocTracking = compdoc_tracking_view_factory(CompDoc)
CompDocDocProof = compdoc_docproof_view_factory(CompDoc)
CompDocNotification = compdoc_notification_view_factory(CompDoc)
CompDocNotificationDraft = compdoc_notification_draft_view_factory(CompDoc)
CompDocTransition = transition_view_factory(CompDoc)
CompDocWork = work_view_factory(CompDoc)
CompDocActivity = activity_view_factory(CompDoc)
CompDocArchive = archive_view_factory(CompDoc, True)
CompDocRestore = archive_view_factory(CompDoc, False)
CompDocReviews = review_view_factory(CompDoc)
CompDocReviewDecision = review_decision_view_factory(CompDoc)
CompDocAssignees = assignee_view_factory(CompDoc)
CompDocBulk = bulk_view_factory(CompDoc)
