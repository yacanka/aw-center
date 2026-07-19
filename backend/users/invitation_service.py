import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from .models import UserInvitation

User = get_user_model()
INVITATION_LIFETIME = timedelta(days=1)
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,100}$")


class InvitationInvalid(NotFound):
    """Hide whether an unknown or malformed invitation ever existed."""

    default_detail = "This invitation link is invalid."
    default_code = "INVITATION_INVALID"


class InvitationUnavailable(APIException):
    """Represent a known invitation that can no longer be accepted."""

    status_code = 410
    default_detail = "This invitation is no longer available."
    default_code = "INVITATION_UNAVAILABLE"


def create_invitation(actor, email, group_ids):
    """Create an email-bound invitation and return its one-time raw link."""

    normalized_email = str(email).strip().casefold()
    ensure_email_available(normalized_email)
    groups = resolve_groups(group_ids)
    token = secrets.token_urlsafe(32)
    try:
        invitation = persist_invitation(actor, normalized_email, token, groups)
    except IntegrityError as error:
        raise ValidationError({"email": "An invitation is already being created."}) from error
    return invitation, build_invitation_link(token)


@transaction.atomic
def persist_invitation(actor, email, token, groups):
    """Revoke older links and persist one current invitation atomically."""

    now = timezone.now()
    open_invitations = UserInvitation.objects.select_for_update().filter(
        email__iexact=email, used_at__isnull=True, revoked_at__isnull=True
    )
    open_invitations.update(revoked_at=now)
    invitation = UserInvitation.objects.create(
        token_digest=token_digest(token),
        email=email,
        created_by=actor,
        expires_at=now + INVITATION_LIFETIME,
    )
    invitation.groups.set(groups)
    return invitation


def inspect_invitation(token):
    """Resolve a token and return a currently usable invitation."""

    invitation = find_invitation(token)
    ensure_invitation_available(invitation)
    return invitation


def accept_invitation(token, account_data):
    """Consume one invitation and create its account under a row lock."""

    try:
        with transaction.atomic():
            invitation = find_invitation(token, lock=True)
            ensure_invitation_available(invitation)
            ensure_email_available(invitation.email)
            user = create_invited_user(invitation, account_data)
            mark_invitation_used(invitation, user)
            return user
    except IntegrityError as error:
        raise ValidationError({"username": "This username is no longer available."}) from error


def create_invited_user(invitation, account_data):
    """Create an active user with only the groups selected by the administrator."""

    user = User.objects.create_user(
        username=account_data["username"],
        email=invitation.email,
        first_name=account_data["first_name"],
        last_name=account_data["last_name"],
        password=account_data["password"],
    )
    user.groups.set(invitation.groups.all())
    return user


def mark_invitation_used(invitation, user):
    """Record terminal invitation consumption without retaining the raw token."""

    invitation.used_at = timezone.now()
    invitation.used_by = user
    invitation.save(update_fields=["used_at", "used_by"])


def find_invitation(token, lock=False):
    """Find an invitation by a validated token digest."""

    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise InvitationInvalid()
    queryset = UserInvitation.objects.select_for_update() if lock else UserInvitation.objects
    try:
        return queryset.get(token_digest=token_digest(token))
    except UserInvitation.DoesNotExist as error:
        raise InvitationInvalid() from error


def ensure_invitation_available(invitation):
    """Reject consumed, revoked, or expired invitations with stable codes."""

    if invitation.used_at:
        raise InvitationUnavailable("This invitation has already been used.", "INVITATION_USED")
    if invitation.revoked_at:
        raise InvitationUnavailable("This invitation has been replaced.", "INVITATION_REVOKED")
    if invitation.expires_at <= timezone.now():
        raise InvitationUnavailable("This invitation has expired.", "INVITATION_EXPIRED")


def ensure_email_available(email):
    """Prevent invitations or accounts for an already registered email address."""

    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "An account already uses this email address."})


def resolve_groups(group_ids):
    """Resolve a deduplicated group allowlist selected by the administrator."""

    unique_ids = set(group_ids or [])
    groups = list(Group.objects.filter(pk__in=unique_ids))
    if len(groups) != len(unique_ids):
        raise ValidationError({"group_ids": "One or more selected groups do not exist."})
    return groups


def build_invitation_link(token):
    """Keep the raw token in the URL fragment so proxies never receive it."""

    return f"{settings.FRONTEND_INVITATION_URL.rstrip('/')}#{token}"


def token_digest(token):
    """Return the irreversible database representation of a raw invitation token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
