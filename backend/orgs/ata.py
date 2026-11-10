"""Canonical ATA chapter parsing shared by organization-backed features."""

from numbers import Real
import math
import re


def normalize_ata_chapter(value) -> str:
    """Normalize numeric chapters to ``XX-XX`` and preserve digit-free text."""

    if value is None or isinstance(value, bool):
        raise ValueError("ATA chapter is empty or invalid.")
    if isinstance(value, Real):
        if not math.isfinite(float(value)) or not float(value).is_integer():
            raise ValueError("ATA chapter must be a whole chapter number.")
        text = str(int(value))
    else:
        text = str(value).strip()

    if not text:
        raise ValueError("ATA chapter is empty or invalid.")
    if not any(character.isdigit() for character in text):
        return text

    text = re.sub(
        r"^(?:ata(?:\s+chapter)?|chapter)\s*(?:no|number|numarası|numarasi)?\s*[:#-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if match := re.fullmatch(r"(\d{1,2})", text):
        return f"{int(match.group(1)):02d}-00"
    if match := re.fullmatch(r"(\d{2})(\d{2})", text):
        return f"{match.group(1)}-{match.group(2)}"
    if match := re.fullmatch(r"(\d{1,2})\s*[-./]\s*(\d{1,2})", text):
        return f"{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    raise ValueError("ATA chapter must use a supported numeric format.")


def validate_ata_chapter(value):
    """Require canonical numeric chapters or nonempty digit-free text."""
    from django.core.exceptions import ValidationError

    try:
        normalized = normalize_ata_chapter(value)
    except ValueError as error:
        raise ValidationError("Use an ATA chapter such as 27-00 or digit-free text.") from error
    if normalized != value:
        raise ValidationError("Use a normalized ATA chapter such as 27-00 or digit-free text.")
