"""Numeric Turkish display formats, independent of interface language."""

from django.conf.locale.tr.formats import (
    DATE_INPUT_FORMATS as DEFAULT_DATE_INPUT_FORMATS,
    DATETIME_INPUT_FORMATS as DEFAULT_DATETIME_INPUT_FORMATS,
)

DATE_FORMAT = "d.m.Y"
SHORT_DATE_FORMAT = "d.m.Y"
DATETIME_FORMAT = "d.m.Y H:i:s"
SHORT_DATETIME_FORMAT = "d.m.Y H:i"
TIME_FORMAT = "H:i:s"

# Prefer Turkish form rendering while retaining Django's accepted ISO/legacy inputs.
DATE_INPUT_FORMATS = ["%d.%m.%Y", *DEFAULT_DATE_INPUT_FORMATS]
DATETIME_INPUT_FORMATS = [
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    *DEFAULT_DATETIME_INPUT_FORMATS,
]
