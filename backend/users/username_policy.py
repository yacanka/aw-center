"""Canonical six-character username format."""

import re

from django.core.exceptions import ValidationError


USERNAME_PATTERN = re.compile(r"^[A-Za-zÇĞİÖŞÜçğıöşü][0-9]{5}$")
USERNAME_MESSAGE = "Use one letter followed by exactly five digits (for example, U12345)."


def validate_username_format(value):
    """Require a letter followed by five digits for every submitted username."""

    if not USERNAME_PATTERN.fullmatch(value):
        raise ValidationError(USERNAME_MESSAGE, code="invalid_username_format")
