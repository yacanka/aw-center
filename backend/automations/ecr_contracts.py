"""Validation and safe API errors for the ECR workflow."""

from rest_framework.exceptions import APIException


class EcrVersionConflict(APIException):
    status_code = 409
    default_code = "ECR_VERSION_CONFLICT"
    default_detail = "The ECR workflow changed. Refresh it before continuing."


class EcrStateConflict(APIException):
    status_code = 409
    default_code = "ECR_STATE_CONFLICT"
    default_detail = "The ECR workflow is not in a state that accepts this action."


class EcrPdfInvalid(APIException):
    status_code = 422
    default_code = "ECR_PDF_INVALID"
    default_detail = "The PDF does not contain a supported ECR document."


def ecr_parent_description(snapshot):
    """Render the bounded parent-issue description used by preflight and publication."""

    labels = (
        ("ECR number", "ecr_number"),
        ("Title", "title"),
        ("Project", "project"),
        ("Change class", "change_class"),
        ("Change type", "change_type"),
        ("Effectivity", "effectivity"),
        ("Track type", "track_type"),
        ("Record of change", "record_of_change"),
        ("Requestor", "requestor"),
        ("Originator", "originator"),
        ("ATA", "ata"),
        ("Sub-ATA", "subata"),
        ("Initiator", "initiator"),
        ("Justification", "justification"),
        ("Proposed solution", "proposed_solution"),
        ("Consequence of nonimplementation", "nonimplementation_consequence"),
        ("Impacted groups", "impacted_groups"),
    )
    return "\n".join(f"{label}: {snapshot.get(key, '')}" for label, key in labels)[:30000]


def validate_ecr_version(actual, expected) -> None:
    """Enforce optimistic concurrency for every workflow mutation."""

    if int(actual) != int(expected):
        raise EcrVersionConflict()
