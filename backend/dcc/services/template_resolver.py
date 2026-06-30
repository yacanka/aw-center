"""Securely resolve DCC document template file paths."""

import os
from pathlib import Path

from django.conf import settings

TEMPLATE_DIR = settings.CUSTOM_TEMPLATE_DIR
ALLOWED_TEMPLATE_EXTENSION = ".docx"


class DccTemplateResolutionError(ValueError):
    """Raised when a DCC template cannot be resolved safely."""


class DccTemplateNotFoundError(DccTemplateResolutionError):
    """Raised when the requested DCC template does not exist."""


class InvalidDccTemplateNameError(DccTemplateResolutionError):
    """Raised when a DCC template name is empty or unsafe."""


def resolve_dcc_template_path(project_definition):
    """Return a safe absolute DCC template path for the project definition."""
    template_name = _validate_template_name(project_definition.dcc_template_name)
    template_directory = Path(TEMPLATE_DIR).resolve()
    template_path = (template_directory / template_name).resolve()
    if not template_path.is_relative_to(template_directory):
        raise InvalidDccTemplateNameError("DCC template path is outside the allowed directory.")
    if not template_path.is_file():
        raise DccTemplateNotFoundError("DCC template file was not found.")
    return template_path


def _validate_template_name(template_name):
    normalized_template_name = str(template_name or "").strip()
    if not normalized_template_name:
        raise InvalidDccTemplateNameError("DCC template name must not be empty.")
    if _contains_path_traversal(normalized_template_name):
        raise InvalidDccTemplateNameError("DCC template name must be a plain file name.")
    if Path(normalized_template_name).suffix.lower() != ALLOWED_TEMPLATE_EXTENSION:
        raise InvalidDccTemplateNameError("DCC template must use the .docx extension.")
    return normalized_template_name


def _contains_path_traversal(template_name):
    separators = {os.sep, os.altsep, "/", "\\"} - {None, ""}
    has_separator = any(separator in template_name for separator in separators)
    return has_separator or ".." in Path(template_name).parts
