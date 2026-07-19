"""Safe, cross-platform PowerPoint slide conversion services."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import transaction
from PIL import Image

from .models import Presentation, Slide

try:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore
except ImportError:
    pythoncom = None
    win32com = None


def convert_pptx_to_images(presentation: Presentation, dpi: int = 150) -> None:
    """Convert a presentation with the available platform adapter."""

    _set_status(presentation, "converting")
    try:
        with TemporaryDirectory(prefix="aw-pptx-") as work_directory:
            exporter = _select_exporter()
            images = exporter(presentation, Path(work_directory), dpi)
            _save_slides(presentation, images)
        _set_status(presentation, "ready")
    except Exception:
        _set_status(presentation, "failed")
        raise


def convert_pptx_with_powerpoint(
    presentation: Presentation, work_directory: Path, dpi: int = 150
) -> list[Path]:
    """Export slides with the Windows PowerPoint COM adapter."""

    del dpi
    if win32com is None or pythoncom is None:
        raise RuntimeError("PowerPoint COM conversion is unavailable.")
    output_directory = work_directory / "slides"
    output_directory.mkdir(parents=True, exist_ok=True)
    _powerpoint_export(Path(presentation.file.path), output_directory)
    return sorted(path for path in output_directory.iterdir() if path.suffix.lower() == ".png")


def convert_pptx_with_soffice(
    presentation: Presentation, work_directory: Path, dpi: int = 150
) -> list[Path]:
    """Export slides with bounded LibreOffice and Poppler subprocesses."""

    source_path = Path(presentation.file.path)
    _run_command(_soffice_command(source_path, work_directory))
    pdf_path = work_directory / f"{source_path.stem}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError("LibreOffice did not produce a PDF output.")
    output_base = work_directory / "slide"
    _run_command([settings.PDFTOPPM_BIN, "-png", "-r", str(dpi), str(pdf_path), str(output_base)])
    return sorted(work_directory.glob("slide-*.png"))


def _select_exporter():
    if win32com is not None and pythoncom is not None:
        return convert_pptx_with_powerpoint
    return convert_pptx_with_soffice


def _powerpoint_export(source_path: Path, output_directory: Path) -> None:
    pythoncom.CoInitialize()
    application = None
    opened_presentation = None
    try:
        application = win32com.client.Dispatch("PowerPoint.Application")
        opened_presentation = application.Presentations.Open(str(source_path), WithWindow=False)
        opened_presentation.Export(str(output_directory), "PNG")
    finally:
        if opened_presentation is not None:
            opened_presentation.Close()
        if application is not None:
            application.Quit()
        pythoncom.CoUninitialize()


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


@transaction.atomic
def _save_slides(presentation: Presentation, image_paths: list[Path]) -> None:
    if not image_paths:
        raise RuntimeError("Presentation conversion produced no slides.")
    presentation.slides.all().delete()
    for index, image_path in enumerate(image_paths, start=1):
        _save_slide(presentation, image_path, index)


def _save_slide(presentation: Presentation, image_path: Path, index: int) -> None:
    slides_directory, thumbs_directory = _output_directories()
    slide_name = f"{presentation.id}_{index}.png"
    thumb_name = f"{presentation.id}_{index}_thumb.png"
    with Image.open(image_path) as image:
        image.save(slides_directory / slide_name)
        thumbnail = image.copy()
        thumbnail.thumbnail((512, 512))
        thumbnail.save(thumbs_directory / thumb_name)
    Slide.objects.update_or_create(
        presentation=presentation,
        index=index,
        defaults={"image": f"slides/{slide_name}", "thumb": f"slides/thumbs/{thumb_name}"},
    )


def _output_directories() -> tuple[Path, Path]:
    slides_directory = Path(settings.MEDIA_ROOT) / "slides"
    thumbs_directory = slides_directory / "thumbs"
    slides_directory.mkdir(parents=True, exist_ok=True)
    thumbs_directory.mkdir(parents=True, exist_ok=True)
    return slides_directory, thumbs_directory


def _set_status(presentation: Presentation, status_value: str) -> None:
    presentation.status = status_value
    presentation.save(update_fields=["status"])
