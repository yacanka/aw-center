"""Administrative invitation lifecycle queries and commands."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from .models import UserInvitation


class InvitationCannotRevoke(APIException):
    """Report terminal invitations that cannot transition to revoked."""

    status_code = 409
    default_detail = "This invitation can no longer be revoked."
    default_code = "INVITATION_CANNOT_REVOKE"


def invitation_status(invitation):
    """Return one mutually exclusive invitation lifecycle state."""

    if invitation.used_at:
        return "used"
    if invitation.revoked_at:
        return "revoked"
    if invitation.expires_at <= timezone.now():
        return "expired"
    return "active"


def invitation_queryset(filters):
    """Build an optimized, filtered invitation audit queryset."""

    queryset = UserInvitation.objects.select_related("created_by", "used_by").prefetch_related(
        "groups"
    )
    queryset = filter_by_search(queryset, filters.get("search"))
    return filter_by_status(queryset, filters.get("status"))


def filter_by_search(queryset, search):
    """Match invitation identity and audit actor names."""

    value = (search or "").strip()
    if not value:
        return queryset
    return queryset.filter(
        Q(email__icontains=value)
        | Q(created_by__username__icontains=value)
        | Q(used_by__username__icontains=value)
    )


def filter_by_status(queryset, lifecycle_status):
    """Apply lifecycle predicates using the current database time boundary."""

    now = timezone.now()
    predicates = {
        "active": Q(used_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now),
        "used": Q(used_at__isnull=False),
        "revoked": Q(revoked_at__isnull=False),
        "expired": Q(used_at__isnull=True, revoked_at__isnull=True, expires_at__lte=now),
    }
    return queryset.filter(predicates[lifecycle_status]) if lifecycle_status else queryset


@transaction.atomic
def revoke_invitation(invitation_id):
    """Atomically revoke an active invitation and remain idempotent."""

    invitation = find_invitation_for_update(invitation_id)
    if invitation.revoked_at:
        return invitation
    ensure_revocable(invitation)
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    return invitation


def find_invitation_for_update(invitation_id):
    """Lock one managed invitation or return a stable not-found error."""

    try:
        return UserInvitation.objects.select_for_update().get(pk=invitation_id)
    except UserInvitation.DoesNotExist as error:
        raise NotFound("Invitation not found.", code="INVITATION_NOT_FOUND") from error


def ensure_revocable(invitation):
    """Reject used and expired invitations while allowing idempotent revocation."""

    lifecycle_status = invitation_status(invitation)
    if lifecycle_status == "used":
        raise InvitationCannotRevoke(
            "A used invitation cannot be revoked.", "INVITATION_ALREADY_USED"
        )
    if lifecycle_status == "expired":
        raise InvitationCannotRevoke(
            "An expired invitation cannot be revoked.", "INVITATION_ALREADY_EXPIRED"
        )
