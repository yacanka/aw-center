"""Transaction-bound commands for compliance-document mutations."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from orgs.access_policy import has_project_role
from orgs.models import Person, ProjectRoleAssignment
from integrations.docproof import normalize_document_number, search_document_issue

from .compdoc_workflow import WORKFLOW_STATUSES
from .models import ComplianceDocument, ReviewTask, TrackingProfile, WorkflowEvent


class VersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "VERSION_CONFLICT"
    default_detail = "This compliance document changed after you opened it."


def _lock_document(project, document_id):
    return get_object_or_404(
        ComplianceDocument.objects.select_for_update(),
        project=project,
        pk=document_id,
    )


def _require_active(document):
    if document.is_archived:
        raise ValidationError("Restore the document before changing it.")


def _supersede_pending_reviews(document, user):
    ReviewTask.objects.filter(
        document=document,
        status=ReviewTask.Status.PENDING,
    ).exclude(source_version=document.version).update(
        status=ReviewTask.Status.SUPERSEDED,
        decision_note="Document changed after this review was requested.",
        decided_by=user,
        decided_by_username=user.get_username(),
        decided_at=timezone.now(),
    )


def _require_version(document, expected_version):
    if document.version != expected_version:
        raise VersionConflict()


@transaction.atomic
def update_document(*, project, document_id, expected_version, serializer, user):
    document = _lock_document(project, document_id)
    _require_active(document)
    _require_version(document, expected_version)
    panel = serializer.validated_data.get("panel", document.panel)
    if getattr(panel, "pk", None) != document.panel_id:
        require_tracking_panel_compatibility(document, panel)
    if not _serializer_changes_document(document, serializer.validated_data):
        return document
    serializer.instance = document
    updated = serializer.save(version=document.version + 1)
    _supersede_pending_reviews(updated, user)
    return updated


def require_tracking_panel_compatibility(document, panel):
    """Keep existing tracking recipients valid when a document changes panel."""

    profile = TrackingProfile.objects.filter(document=document).first()
    if profile is None:
        return
    allowed_ids = (
        set(
            Person.objects.filter(responsible_assignments__panel=panel)
            .exclude(email="")
            .values_list("pk", flat=True)
        )
        if panel is not None
        else set()
    )
    selected_ids = set(profile.responsible_people.values_list("pk", flat=True))
    if (
        profile.responsible_mode == TrackingProfile.ResponsibleMode.CUSTOM
        and not selected_ids.issubset(allowed_ids)
    ):
        raise ValidationError(
            {"panel": "Update custom tracking recipients before changing the panel."}
        )
    recipients = (
        allowed_ids
        if profile.responsible_mode == TrackingProfile.ResponsibleMode.AUTOMATIC
        else selected_ids
    )
    if profile.notification_enabled and not recipients:
        raise ValidationError(
            {"panel": "Disable notifications or assign recipients before changing the panel."}
        )


def _serializer_changes_document(document, values):
    for field, value in values.items():
        if field == "cover_page":
            if (
                document.cover_page.number != str(value.get("number", "")).strip()
                or (
                    "issue" in value
                    and document.cover_page.issue != value.get("issue")
                )
            ):
                return True
            continue
        if hasattr(value, "pk"):
            if getattr(document, f"{field}_id") != value.pk:
                return True
        elif getattr(document, field) != value:
            return True
    return False


@transaction.atomic
def transition_document(
    *,
    project,
    document_id,
    expected_version,
    new_status,
    effective_date,
    next_action_due_date,
    reason,
    user,
    source=WorkflowEvent.Source.MANUAL,
):
    document = _lock_document(project, document_id)
    _require_active(document)
    _require_version(document, expected_version)
    if new_status not in WORKFLOW_STATUSES:
        raise ValidationError({"status": "Select a supported workflow status."})
    if new_status == document.status:
        raise ValidationError({"status": "Select a status different from the current status."})

    latest_event = WorkflowEvent.objects.filter(document=document).order_by("-sequence").first()
    sequence = (latest_event.sequence if latest_event else 0) + 1
    if latest_event and effective_date < latest_event.effective_date:
        raise ValidationError(
            {"effective_date": "The effective date cannot precede the latest transition."}
        )
    event = WorkflowEvent.objects.create(
        document=document,
        sequence=sequence,
        previous_status=document.status,
        status=new_status,
        effective_date=effective_date,
        next_action_due_date=next_action_due_date,
        reason=reason,
        source=source,
        actor=user,
        actor_username=user.get_username(),
    )

    document.status = new_status
    document.next_action_due_date = next_action_due_date
    if sequence == 1:
        document.ubm_target_date = effective_date
    elif sequence == 2:
        document.ubm_delivery_date = effective_date
    document.version += 1
    document._history_user = user
    document._change_reason = reason[:100]
    document.save(
        update_fields=[
            "status",
            "next_action_due_date",
            "ubm_target_date",
            "ubm_delivery_date",
            "version",
            "updated_at",
        ]
    )
    _supersede_pending_reviews(document, user)
    return document, event


@transaction.atomic
def update_work(*, project, document_id, expected_version, values, reason, user):
    document = _lock_document(project, document_id)
    _require_active(document)
    _require_version(document, expected_version)
    owner = values.get("owner")
    if owner is not None and not has_project_role(
        owner,
        project,
        ProjectRoleAssignment.Domain.COMPLIANCE,
        ProjectRoleAssignment.Role.VIEWER,
    ):
        raise ValidationError({"owner": "Owner cannot view this project."})
    owner_group = values.get("owner_group")
    if owner_group is not None and not ProjectRoleAssignment.objects.filter(
        project=project,
        domain=ProjectRoleAssignment.Domain.COMPLIANCE,
        group=owner_group,
        role__in=ProjectRoleAssignment.VALID_ROLES[
            ProjectRoleAssignment.Domain.COMPLIANCE
        ],
    ).exists():
        raise ValidationError(
            {"owner_group": "Owner team cannot view this project."}
        )
    changed = []
    for field in ("owner", "owner_group", "next_action_due_date"):
        if field not in values:
            continue
        value = values[field]
        if field in {"owner", "owner_group"}:
            current_value = getattr(document, f"{field}_id")
            next_value = getattr(value, "pk", value)
        else:
            current_value = getattr(document, field)
            next_value = value
        if current_value == next_value:
            continue
        setattr(document, field, value)
        changed.append(field)
    if not changed:
        return document
    document.version += 1
    document._history_user = user
    document._change_reason = reason[:100]
    document.save(update_fields=[*changed, "version", "updated_at"])
    _supersede_pending_reviews(document, user)
    return document


@transaction.atomic
def set_archive_state(
    *,
    project,
    document_id,
    expected_version,
    archived,
    reason,
    user,
):
    document = _lock_document(project, document_id)
    _require_version(document, expected_version)
    if document.is_archived == archived:
        return document
    document.is_archived = archived
    document.archived_at = timezone.now() if archived else None
    document.archived_by = user if archived else None
    document.archive_reason = reason if archived else ""
    document.version += 1
    document._history_user = user
    document._change_reason = reason[:100]
    document.save(
        update_fields=[
            "is_archived",
            "archived_at",
            "archived_by",
            "archive_reason",
            "version",
            "updated_at",
        ]
    )
    if archived:
        ReviewTask.objects.filter(
            document=document,
            status=ReviewTask.Status.PENDING,
        ).update(
            status=ReviewTask.Status.CANCELLED,
            decision_note="Document archived.",
            decided_by=user,
            decided_by_username=user.get_username(),
            decided_at=timezone.now(),
        )
    return document


@transaction.atomic
def update_tracking_profile(
    *,
    project,
    document_id,
    expected_version,
    payload,
    user,
):
    """Persist tracking preferences with document-scoped optimistic fencing."""

    from .serializers import TrackingProfileSerializer

    document = _lock_document(project, document_id)
    if document.is_archived:
        raise ValidationError("Restore the document before changing tracking preferences.")
    profile = (
        TrackingProfile.objects.select_for_update()
        .filter(document=document)
        .first()
    )
    current_version = profile.version if profile is not None else 0
    if current_version != expected_version:
        raise VersionConflict("Tracking preferences changed after you opened them.")
    instance = profile or TrackingProfile(document=document)
    serializer = TrackingProfileSerializer(
        instance,
        data=payload,
        context={"document": document},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(version=current_version + 1, updated_by=user)


def refresh_docproof_tracking(*, project, document_id, expected_version, user):
    """Fetch one DocProof issue, then persist it behind the tracking fence."""

    document = get_object_or_404(
        ComplianceDocument.objects.filter(project=project, is_archived=False),
        pk=document_id,
    )
    current_profile_version = (
        TrackingProfile.objects.filter(document=document)
        .values_list("version", flat=True)
        .first()
        or 0
    )
    if current_profile_version != expected_version:
        raise VersionConflict("Tracking evidence changed after you opened it.")
    document_version = document.version
    document_number = normalize_document_number(document.tech_doc_no or "")
    if not document_number:
        raise ValidationError({"tech_doc_no": "A technical document number is required."})
    issue, failure_reason = search_document_issue(document_number)
    checked_at = timezone.now()
    remote_issue = "" if issue is None else str(issue)
    if failure_reason:
        docproof_status = failure_reason
    elif remote_issue == str(document.tech_doc_issue or "").strip():
        docproof_status = "current"
    else:
        docproof_status = "revision_available"

    with transaction.atomic():
        locked_document = _lock_document(project, document_id)
        _require_active(locked_document)
        if locked_document.version != document_version:
            raise VersionConflict("The document changed while DocProof was checked.")
        profile = TrackingProfile.objects.select_for_update().filter(
            document=locked_document
        ).first()
        current_version = profile.version if profile else 0
        if current_version != expected_version:
            raise VersionConflict("Tracking evidence changed after you opened it.")
        profile = profile or TrackingProfile(document=locked_document)
        profile.docproof_issue = remote_issue
        profile.docproof_status = docproof_status
        profile.docproof_checked_at = checked_at
        profile.version = current_version + 1
        profile.updated_by = user
        profile.save()
        return profile


@transaction.atomic
def request_review(
    *,
    project,
    document_id,
    expected_version,
    kind,
    assignee,
    due_date,
    request_note,
    user,
):
    document = _lock_document(project, document_id)
    _require_active(document)
    _require_version(document, expected_version)
    if not has_project_role(
        assignee,
        project,
        ProjectRoleAssignment.Domain.COMPLIANCE,
        ProjectRoleAssignment.Role.VIEWER,
    ):
        raise ValidationError({"assignee": "Assignee cannot view this project."})
    try:
        return ReviewTask.objects.create(
            document=document,
            kind=kind,
            assignee=assignee,
            assignee_username=assignee.get_username(),
            requested_by=user,
            requested_by_username=user.get_username(),
            due_date=due_date,
            request_note=request_note,
            source_version=document.version,
        )
    except IntegrityError as error:
        raise VersionConflict("An equivalent review is already pending.") from error


@transaction.atomic
def decide_review(*, project, document_id, review_id, decision, note, user):
    task = get_object_or_404(
        ReviewTask.objects.select_for_update().select_related("document"),
        pk=review_id,
        document_id=document_id,
        document__project=project,
    )
    if task.status != ReviewTask.Status.PENDING:
        raise ValidationError({"status": "This task is no longer pending."})
    if task.document.is_archived:
        raise ValidationError("Restore the document before deciding this review.")
    if task.source_version != task.document.version:
        raise VersionConflict("The document changed after this review was requested.")
    is_manager = has_project_role(
        user,
        project,
        ProjectRoleAssignment.Domain.COMPLIANCE,
        ProjectRoleAssignment.Role.MANAGER,
    )
    if decision == ReviewTask.Status.CANCELLED:
        if not is_manager:
            raise PermissionDenied("Only a compliance manager may cancel a review.")
    elif task.assignee_id != user.pk and not is_manager:
        raise PermissionDenied("Only the assignee or a compliance manager may decide this review.")

    task.status = decision
    task.decision_note = note
    task.decided_by = user
    task.decided_by_username = user.get_username()
    task.decided_at = timezone.now()
    task.save(
        update_fields=[
            "status",
            "decision_note",
            "decided_by",
            "decided_by_username",
            "decided_at",
        ]
    )
    return task
