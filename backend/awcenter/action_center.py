"""Permission-aware attention signals spanning AW Center workflows."""

from datetime import timedelta

from django.db.models import Subquery
from django.utils import timezone

from common.models import CompDocImportAudit
from dcc.issue_draft_models import JiraIssueDraft, JiraIssueDraftStatus
from jobs.models import Job, JobStatus
from jobs.recovery import recovery_hint
from users.models import UserInvitation

from .action_center_decisions import filter_user_decisions

MAX_SOURCE_ITEMS = 6
MAX_ITEMS = 12
RECENT_WINDOW = timedelta(days=14)
INVITATION_WARNING_WINDOW = timedelta(hours=6)
SEVERITY_ORDER = {"critical": 0, "warning": 1}

def build_action_center(user):
    """Return one user's bounded and decision-filtered attention payload."""

    items = sorted(available_items(user), key=item_sort_key)
    visible_items = filter_user_decisions(user, items)[:MAX_ITEMS]
    return {
        "generated_at": timezone.now(),
        "summary": item_summary(visible_items),
        "items": [public_item(item) for item in visible_items],
    }


def available_items(user):
    """Return all currently authorized attention candidates for one user."""

    items = job_items(user)
    items.extend(jira_draft_items(user))
    if user.has_perm("common.view_compdocimportaudit"):
        items.extend(import_items())
    if can_manage_invitations(user):
        items.extend(invitation_items())
    return items


def job_items(user):
    """Return unresolved recent failures owned by the current user."""

    retried_ids = Job.objects.filter(owner=user, retry_of__isnull=False).values("retry_of_id")
    jobs = (
        Job.objects.filter(
            owner=user,
            status=JobStatus.FAILED,
            updated_at__gte=recent_boundary(),
        )
        .exclude(pk__in=Subquery(retried_ids))
        .order_by("-updated_at")[:MAX_SOURCE_ITEMS]
    )
    return [job_item(job) for job in jobs]


def job_item(job):
    """Convert one safe job failure into an attention item."""

    can_retry = job.retryable and job.attempt < job.max_attempts
    return attention_item(
        identifier=f"job:{job.pk}",
        kind="job",
        severity="critical",
        title=job.title,
        detail=job.error_code or "Background operation failed.",
        guidance=recovery_hint(job.error_code),
        action_label="Retry or review" if can_retry else "Review job",
        action_path=f"/jobs?job={job.pk}",
        occurred_at=job.updated_at,
    )


def jira_draft_items(user):
    """Return approved or failed bridge drafts that still need a human action."""

    drafts = JiraIssueDraft.objects.filter(
        owner=user,
        status__in=[JiraIssueDraftStatus.APPROVED, JiraIssueDraftStatus.FAILED],
        updated_at__gte=recent_boundary(),
    ).order_by("-updated_at")[:MAX_SOURCE_ITEMS]
    return [jira_draft_item(draft) for draft in drafts]


def jira_draft_item(draft):
    """Convert one unresolved JIRA bridge state into a safe attention item."""

    failed = draft.status == JiraIssueDraftStatus.FAILED
    return attention_item(
        identifier=f"jira-draft:{draft.pk}", kind="jira_draft",
        severity="critical" if failed else "warning",
        title=draft.summary, detail=draft.last_error_code or "Approved draft awaits publication.",
        guidance=("Verify the JIRA session and safely retry." if failed
                  else "Publish the approved version or revise it before sending."),
        action_label="Review JIRA draft", action_path=f"/jobs?job={draft.source_job_id}",
        occurred_at=draft.updated_at,
    )


def import_items():
    """Return recent failed or partially rejected import audits."""

    audits = CompDocImportAudit.objects.filter(
        status__in=[CompDocImportAudit.Status.FAILED, CompDocImportAudit.Status.PARTIAL],
        started_at__gte=recent_boundary(),
    ).order_by("-started_at")[:MAX_SOURCE_ITEMS]
    return [import_item(audit) for audit in audits]


def import_item(audit):
    """Convert one sanitized import audit into an attention item."""

    failed = audit.status == CompDocImportAudit.Status.FAILED
    detail = f"{audit.rejected_count} of {audit.total_rows} rows rejected."
    return attention_item(
        identifier=f"import:{audit.pk}",
        kind="import",
        severity="critical" if failed else "warning",
        title=f"CompDoc import: {audit.source_filename}",
        detail=detail,
        guidance="Review the rejected rows, download the remediation report, and import again.",
        action_label="Review import",
        action_path=f"/compdocs/{audit.project_slug}?audit={audit.pk}",
        occurred_at=audit.started_at,
    )


def invitation_items():
    """Return active invitations approaching their expiry boundary."""

    now = timezone.now()
    invitations = UserInvitation.objects.filter(
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=now,
        expires_at__lte=now + INVITATION_WARNING_WINDOW,
    ).order_by("expires_at")[:MAX_SOURCE_ITEMS]
    return [invitation_item(invitation) for invitation in invitations]


def invitation_item(invitation):
    """Convert one expiring invitation into an administrator action."""

    return attention_item(
        identifier=f"invitation:{invitation.pk}",
        kind="invitation",
        severity="warning",
        title=f"Invitation expires soon: {invitation.email}",
        detail="The invitation will expire within six hours.",
        guidance="Confirm delivery or create a replacement link before it expires.",
        action_label="Manage invitations",
        action_path="/users?invitations=active",
        occurred_at=invitation.created_at,
        due_at=invitation.expires_at,
    )


def attention_item(**values):
    """Attach an internal timestamp used only for deterministic ranking."""

    values["id"] = values.pop("identifier")
    return {**values, "_sort_at": values["occurred_at"]}


def item_sort_key(item):
    """Sort critical signals first and newest signals first within severity."""

    return SEVERITY_ORDER[item["severity"]], -item["_sort_at"].timestamp()


def public_item(item):
    """Remove internal ranking metadata from one response item."""

    return {key: value for key, value in item.items() if not key.startswith("_")}


def item_summary(items):
    """Count visible attention items by severity."""

    critical = sum(item["severity"] == "critical" for item in items)
    warning = sum(item["severity"] == "warning" for item in items)
    return {"total": len(items), "critical": critical, "warning": warning}


def can_manage_invitations(user):
    """Mirror the invitation API's delegated administrator boundary."""

    return bool(user.is_staff and user.has_perm("auth.add_user"))


def recent_boundary():
    """Return the bounded action-center history window."""

    return timezone.now() - RECENT_WINDOW
