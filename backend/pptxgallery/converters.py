"""Bounded Linux presentation rendering and image normalization."""

import subprocess
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image


def render_pptx_to_images(
    source_path: Path,
    work_directory: Path,
    dpi: int = 150,
) -> list[Path]:
    """Render a PPTX to bounded PNG slide files through LibreOffice/Poppler."""

    _run_command(_soffice_command(source_path, work_directory))
    pdf_path = work_directory / f"{source_path.stem}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError("LibreOffice did not produce a PDF output.")
    output_base = work_directory / "slide"
    _run_command(
        [settings.PDFTOPPM_BIN, "-png", "-r", str(dpi), str(pdf_path), str(output_base)]
    )
    images = sorted(work_directory.glob("slide-*.png"))
    if not images:
        raise RuntimeError("Presentation conversion produced no slides.")
    return images


def normalized_slide_payloads(source) -> tuple[bytes, bytes]:
    """Decode and re-encode one slide and its thumbnail as safe PNG data."""

    with Image.open(source) as image:
        image.load()
        normalized = image.convert("RGB")
        full_output = BytesIO()
        normalized.save(full_output, format="PNG", optimize=True)
        thumbnail = normalized.copy()
        thumbnail.thumbnail((512, 512))
        thumb_output = BytesIO()
        thumbnail.save(thumb_output, format="PNG", optimize=True)
    return full_output.getvalue(), thumb_output.getvalue()


def _soffice_command(source_path: Path, work_directory: Path) -> list[str]:
    return [
        settings.SOFFICE_BIN,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(work_directory),
        str(source_path),
    ]


def _run_command(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=settings.PPTX_CONVERSION_TIMEOUT_SECONDS,
    )
