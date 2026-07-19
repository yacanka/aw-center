from pathlib import Path

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.worker import update_progress
from word.service.translator import get_text_generator

SUPPORTED_TRANSLATIONS = {"tr2en": "TR-EN", "en2tr": "EN-TR"}


def execute_word_translation(job):
    """Translate one Word document into an owned durable artifact."""

    translation_type = validate_translation_type(job.parameters.get("translate_type"))
    input_path = materialize_job_input(job)
    output_path = temporary_output(".docx")
    result_ready = False
    try:
        translate_document(job.id, input_path, output_path, translation_type)
        filename = translated_filename(job.input_name, translation_type)
        result_ready = True
        return JobExecutionResult(output_path, filename, "Word translation completed.")
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def translate_document(job_id, input_path, output_path, translation_type):
    """Execute local-model translation while publishing global progress."""

    try:
        translator = get_text_generator(translation_type)
        with input_path.open("rb") as source:
            results = translator.translate_docx_req(source)
            write_translation_results(job_id, results, output_path)
    except (ImportError, OSError) as error:
        raise JobExecutionFailure(
            "The configured translation model is unavailable.", "WORD_MODEL_UNAVAILABLE", True
        ) from error


def write_translation_results(job_id, results, output_path):
    """Persist translator output and turn generator progress into job events."""

    output_buffer = None
    for result_type, item in results:
        if result_type == "progress":
            index, total, paragraph_type = item
            progress = 10 + int(index / max(1, total) * 80)
            update_progress(job_id, progress, f"Translating {paragraph_type} ({index}/{total}).")
        elif result_type == "result":
            output_buffer = item
    if output_buffer is None:
        raise JobExecutionFailure("Translation produced no document.", "WORD_OUTPUT_MISSING")
    output_path.write_bytes(output_buffer.getvalue())


def validate_translation_type(value):
    """Return an allowlisted translation direction."""

    normalized = str(value or "").lower()
    if normalized not in SUPPORTED_TRANSLATIONS:
        raise JobExecutionFailure("Unsupported translation direction.", "WORD_DIRECTION_INVALID")
    return normalized


def translated_filename(input_name, translation_type):
    """Build a bounded user-facing translated document filename."""

    stem = Path(input_name).stem[:100]
    return f"[{SUPPORTED_TRANSLATIONS[translation_type]}] {stem}.docx"
