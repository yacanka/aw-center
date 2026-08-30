"""Durable presentation conversion executor."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.db import transaction

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.execution import current_execution_lease, lock_active_execution, update_progress
from jobs.storage import private_job_storage

from .converters import normalized_slide_payloads, render_pptx_to_images
from .models import Presentation, Slide


def execute_presentation_conversion(job):
    """Render one owned presentation and fence private slide publication."""

    input_path = materialize_job_input(job)
    receipt_path = temporary_output(".json")
    staged_names: list[str] = []
    published = False
    result_ready = False
    try:
        presentation = _adopt_conversion_job(job)
        update_progress(job.id, 10, "Presentation input verified.")
        with TemporaryDirectory(prefix="aw-presentation-") as work_directory:
            image_paths = render_pptx_to_images(input_path, Path(work_directory))
            staged = _store_generated_slides(job, presentation, image_paths, staged_names)
        update_progress(job.id, 85, "Generated slides verified.")
        _publish_slides(job, presentation, staged)
        published = True
        receipt = {
            "presentation_id": str(presentation.id),
            "slide_count": len(staged),
            "status": "ready",
        }
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        result_ready = True
        return JobExecutionResult(
            receipt_path,
            "presentation-conversion.json",
            "Presentation conversion completed.",
            receipt,
        )
    except JobExecutionFailure:
        raise
    except Exception as error:
        raise JobExecutionFailure(
            "Presentation conversion failed.",
            "PRESENTATION_CONVERSION_FAILED",
            retryable=True,
        ) from error
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            receipt_path.unlink(missing_ok=True)
        if not published:
            _delete_private_files(staged_names)


@transaction.atomic
def _adopt_conversion_job(job) -> Presentation:
    lease = current_execution_lease(job.id)
    lock_active_execution(lease)
    try:
        presentation = Presentation.objects.select_for_update().get(
            pk=job.parameters.get("presentation_id"),
            owner_id=job.owner_id,
        )
    except (Presentation.DoesNotExist, TypeError, ValueError) as error:
        raise JobExecutionFailure(
            "Presentation conversion target is unavailable.",
            "PRESENTATION_NOT_FOUND",
        ) from error
    if presentation.conversion_job_id != job.id:
        if not job.retry_of_id or presentation.conversion_job_id != job.retry_of_id:
            raise JobExecutionFailure(
                "Presentation conversion was replaced by a newer request.",
                "PRESENTATION_JOB_REPLACED",
            )
        presentation.conversion_job = job
    presentation.status = "converting"
    presentation.save(update_fields=["conversion_job", "status"])
    return presentation


def _store_generated_slides(job, presentation, image_paths, staged_names):
    staged = []
    for index, image_path in enumerate(image_paths, start=1):
        image_bytes, thumb_bytes = normalized_slide_payloads(image_path)
        base = (
            f"presentations/{presentation.owner_id}/{presentation.id}/"
            f"executions/{job.id}"
        )
        image_name = private_job_storage.save(
            f"{base}/slides/{index}.png",
            ContentFile(image_bytes),
        )
        staged_names.append(image_name)
        thumb_name = private_job_storage.save(
            f"{base}/thumbs/{index}.png",
            ContentFile(thumb_bytes),
        )
        staged_names.append(thumb_name)
        staged.append(
            {
                "index": index,
                "image": image_name,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "thumb": thumb_name,
                "thumb_sha256": hashlib.sha256(thumb_bytes).hexdigest(),
            }
        )
    return staged


@transaction.atomic
def _publish_slides(job, presentation, staged):
    lease = current_execution_lease(job.id)
    lock_active_execution(lease)
    locked = Presentation.objects.select_for_update().get(
        pk=presentation.pk,
        owner_id=job.owner_id,
        conversion_job_id=job.id,
    )
    locked.slides.all().delete()
    Slide.objects.bulk_create(
        [Slide(presentation=locked, **slide_data) for slide_data in staged]
    )
    locked.status = "ready"
    locked.save(update_fields=["status"])


def _delete_private_files(names):
    for name in names:
        if name:
            private_job_storage.delete(name)
