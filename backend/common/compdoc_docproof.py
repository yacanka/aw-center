"""Persisted DocProof status checks for compliance documents."""

import logging

from django.utils import timezone
from requests.exceptions import HTTPError, RequestException
from rest_framework.exceptions import APIException, ValidationError

from common.compdoc_tracking_models import CompDocTrackingProfile
from docproof.client import login, normalize_document_number, search_issue_number

LOGGER = logging.getLogger(__name__)


class CompDocDocProofUnavailable(APIException):
    """Report a retryable integration failure without leaking upstream details."""

    status_code = 503
    default_code = "COMPDOC_DOCPROOF_UNAVAILABLE"
    default_detail = "DocProof could not be reached."


def check_docproof(model, document, user=None):
    """Check and persist the latest published issue for one document."""

    number = normalize_document_number(str(document.tech_doc_no or ""))
    if not number:
        raise ValidationError({"tech_doc_no": "A technical document number is required."})
    try:
        issue, failure = _search_with_session_refresh(number)
    except RequestException as exception:
        LOGGER.warning("CompDoc DocProof check failed: %s", exception.__class__.__name__)
        raise CompDocDocProofUnavailable() from exception
    profile = _tracking_profile(model, document)
    _update_profile(profile, issue, failure, document.tech_doc_issue, user)
    return profile


def _tracking_profile(model, document):
    profile, _created = CompDocTrackingProfile.objects.get_or_create(
        project_slug=model._meta.app_label,
        document_id=document.pk,
    )
    return profile


def _update_profile(profile, issue, failure, known_issue, user):
    previous_issue = profile.docproof_issue
    previous_status = profile.docproof_status
    checked_at = timezone.now()
    profile.docproof_issue = "" if issue is None else str(issue)
    profile.docproof_status = _status(issue, failure, known_issue)
    profile.docproof_checked_at = checked_at
    profile.docproof_issue_detected_at = _detected_at(
        profile, previous_issue, previous_status, checked_at
    )
    profile.updated_by = user or profile.updated_by
    profile.save()


def _search_with_session_refresh(number):
    try:
        return search_issue_number(number)
    except HTTPError:
        login()
        return search_issue_number(number)


def _status(issue, failure, known_issue):
    if failure == "missing":
        return "not_found"
    if failure == "unpublished":
        return "unpublished"
    if issue in (None, 0, ""):
        return "issue_unavailable"
    if _issue_token(issue) != _issue_token(known_issue):
        return "revision_available"
    return "current"


def _issue_token(value):
    text = str(value or "").strip()
    try:
        number = float(text)
        return str(int(number)) if number.is_integer() else str(number)
    except ValueError:
        return text.casefold()


def _detected_at(profile, previous_issue, previous_status, checked_at):
    if profile.docproof_status != "revision_available":
        return None
    same_revision = (
        previous_status == "revision_available"
        and _issue_token(previous_issue) == _issue_token(profile.docproof_issue)
    )
    if same_revision and profile.docproof_issue_detected_at:
        return profile.docproof_issue_detected_at
    return checked_at
