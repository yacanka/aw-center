"""Responsible resolution and API projections for CompDoc tracking."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from common.compdoc_notification_events import EVENT_KEYS, EVENT_OPTIONS, event_states
from common.compdoc_notification_policy import delivery_event_states
from common.compdoc_tracking_models import CompDocTrackingProfile


def tracking_payload(model, document, profile=None):
    """Return a safe tracking workspace payload for one document."""

    active_profile = profile or find_profile(model, document.pk)
    contacts = resolve_contacts(model, document, active_profile)
    return {
        "document": _document_payload(document),
        "responsible_mode": _profile_value(active_profile, "responsible_mode", "automatic"),
        "responsible_person_ids": [contact["id"] for contact in contacts],
        "responsibles": contacts,
        "candidate_responsibles": candidate_contacts(model, document),
        "notification_enabled": _profile_value(active_profile, "notification_enabled", False),
        "notification_events": _profile_value(active_profile, "notification_events", []),
        "configured": active_profile is not None,
        "event_options": EVENT_OPTIONS,
        "event_states": _delivery_states(model, document, active_profile, contacts),
        "docproof": _docproof_payload(active_profile),
        "recent_notifications": recent_notifications(active_profile),
    }


@transaction.atomic
def update_tracking_profile(model, document, data, user):
    """Validate and persist user-owned tracking choices."""

    mode = data["responsible_mode"]
    person_ids = _validate_person_ids(model, document, mode, data["responsible_person_ids"])
    events = _validate_events(data["notification_events"])
    _validate_notification_readiness(model, document, mode, person_ids, events, data)
    profile, _created = CompDocTrackingProfile.objects.select_for_update().get_or_create(
        project_slug=model._meta.app_label,
        document_id=document.pk,
    )
    profile.responsible_mode = mode
    profile.responsible_person_ids = person_ids
    profile.notification_enabled = data["notification_enabled"]
    profile.notification_events = events
    profile.updated_by = user
    profile.save()
    return profile


def find_profile(model, document_id):
    """Return the optional profile associated with one concrete project row."""

    return CompDocTrackingProfile.objects.filter(
        project_slug=model._meta.app_label,
        document_id=document_id,
    ).first()


@transaction.atomic
def delete_document_and_tracking(model, document):
    """Delete one document and its project-neutral tracking profile atomically."""

    document_id = document.pk
    document.delete()
    CompDocTrackingProfile.objects.filter(
        project_slug=model._meta.app_label,
        document_id=document_id,
    ).delete()


def candidate_contacts(model, document):
    """Return all project responsibles matching the document ATA chapter."""

    responsible_model = model._meta.apps.get_model(model._meta.app_label, "Responsible")
    queryset = responsible_model.objects.select_related("panel", "person").filter(
        panel__ata__iexact=str(document.ata or "")
    )
    return [_contact_payload(person) for person in queryset]


def resolve_contacts(model, document, profile):
    """Resolve automatic or explicitly selected current organization contacts."""

    candidates = candidate_contacts(model, document)
    if not profile or profile.responsible_mode == CompDocTrackingProfile.ResponsibleMode.AUTOMATIC:
        return candidates
    selected = {int(value) for value in profile.responsible_person_ids if str(value).isdigit()}
    return [contact for contact in candidates if contact["id"] in selected]


def recent_notifications(profile):
    """Return bounded, content-free delivery history."""

    if not profile or not profile.pk:
        return []
    return [_notification_payload(item) for item in profile.notification_logs.all()[:10]]


def _validate_person_ids(model, document, mode, values):
    if mode == CompDocTrackingProfile.ResponsibleMode.AUTOMATIC:
        return []
    requested = {int(value) for value in values}
    available = {contact["id"] for contact in candidate_contacts(model, document)}
    if not requested.issubset(available):
        raise ValidationError(
            {"responsible_person_ids": "Select only responsibles assigned to this ATA chapter."}
        )
    return sorted(requested)


def _validate_events(values):
    invalid = set(values) - EVENT_KEYS
    if invalid:
        raise ValidationError({"notification_events": "Select supported notification events."})
    return sorted(set(values))


def _validate_notification_readiness(model, document, mode, person_ids, events, data):
    if not data["notification_enabled"]:
        return
    if not events:
        raise ValidationError({"notification_events": "Choose at least one notification event."})
    candidates = candidate_contacts(model, document)
    has_recipients = bool(candidates) if mode == "automatic" else bool(person_ids)
    if not has_recipients:
        raise ValidationError(
            {"responsible_person_ids": "Assign at least one ATA responsible before enabling alerts."}
        )


def _contact_payload(person):
    return {
        "id": person.pk,
        "name": person.name,
        "email": person.email,
        "title": person.title,
        "panel": person.panel.ata if person.panel_id else "",
        "panel_name": person.panel.name if person.panel_id else "",
    }


def _delivery_states(model, document, profile, contacts):
    return delivery_event_states(
        model._meta.app_label,
        event_states(document, profile),
        contacts,
        document,
        profile,
    )


def _notification_payload(item):
    return {
        "id": str(item.id),
        "event_type": item.event_type,
        "status": item.status,
        "recipient_count": item.recipient_count,
        "primary_recipient_count": item.primary_recipient_count,
        "escalation_recipient_count": item.escalation_recipient_count,
        "policy_version": item.policy_version,
        "attempt_count": item.attempt_count,
        "error_code": item.error_code,
        "created_at": item.created_at,
        "sent_at": item.sent_at,
    }


def _document_payload(document):
    return {
        "id": str(document.pk),
        "name": document.name,
        "ata": document.ata,
        "panel": document.panel,
        "tech_doc_no": document.tech_doc_no,
        "tech_doc_issue": document.tech_doc_issue,
        "delivered_tech_doc_issue": document.delivered_tech_doc_issue,
        "status": document.status,
        "ubm_target_date": document.ubm_target_date,
    }


def _docproof_payload(profile):
    return {
        "status": _profile_value(profile, "docproof_status", "never_checked"),
        "issue": _profile_value(profile, "docproof_issue", ""),
        "checked_at": _profile_value(profile, "docproof_checked_at", None),
    }


def _profile_value(profile, name, default):
    return getattr(profile, name, default) if profile else default
