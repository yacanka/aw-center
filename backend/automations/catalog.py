"""Canonical, import-free metadata for durable job executors."""

from dataclasses import dataclass

from awcenter.file_security import (
    MEDIA_POLICY,
    MSG_POLICY,
    OOXML_WORKBOOK_POLICY,
    PRESENTATION_POLICY,
    WORD_DOCUMENT_POLICY,
    UploadPolicy,
)

LOCAL_QUEUE = "local"
DOORS_QUEUE = "doors"
SUPPORTED_QUEUES = frozenset({LOCAL_QUEUE, DOORS_QUEUE})
JSON_OPERATION_POLICY = UploadPolicy(
    frozenset({".json"}),
    "DOORS_RUNNER_MAX_INPUT_BYTES",
    1024 * 1024,
)


@dataclass(frozen=True)
class ExecutorMetadata:
    """Describe one allowlisted executor without importing its feature module."""

    kind: str
    dotted_path: str
    queue: str
    upload_policy: UploadPolicy | None
    timeout_seconds: int


EXECUTOR_CATALOG = (
    ExecutorMetadata(
        kind="dcc.create_document",
        dotted_path="dcc.document_job.execute_dcc_document_creation",
        queue=LOCAL_QUEUE,
        upload_policy=None,
        timeout_seconds=180,
    ),
    ExecutorMetadata(
        kind="dcc.publish_jira_draft",
        dotted_path="dcc.publication_executor.execute_jira_draft_publication",
        queue=LOCAL_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=180,
    ),
    ExecutorMetadata(
        kind="automations.publish_ecr_jira",
        dotted_path="automations.ecr_publication_executor.execute_ecr_jira_publication",
        queue=LOCAL_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=300,
    ),
    ExecutorMetadata(
        kind="excel.cover_pages",
        dotted_path="excel.cover_pages.execute_cover_page_creation",
        queue=LOCAL_QUEUE,
        upload_policy=OOXML_WORKBOOK_POLICY,
        timeout_seconds=900,
    ),
    ExecutorMetadata(
        kind="media.convert",
        dotted_path="media_tools.job_executor.execute_media_conversion",
        queue=LOCAL_QUEUE,
        upload_policy=MEDIA_POLICY,
        timeout_seconds=900,
    ),
    ExecutorMetadata(
        kind="outlook.extract_word_attachment",
        dotted_path="outlook.job_executor.execute_word_attachment_extraction",
        queue=LOCAL_QUEUE,
        upload_policy=MSG_POLICY,
        timeout_seconds=300,
    ),
    ExecutorMetadata(
        kind="word.analyze",
        dotted_path="word.analysis.execute_document_analysis",
        queue=LOCAL_QUEUE,
        upload_policy=WORD_DOCUMENT_POLICY,
        timeout_seconds=900,
    ),
    ExecutorMetadata(
        kind="word.translate",
        dotted_path="word.job_executor.execute_word_translation",
        queue=LOCAL_QUEUE,
        upload_policy=WORD_DOCUMENT_POLICY,
        timeout_seconds=900,
    ),
    ExecutorMetadata(
        kind="presentations.convert",
        dotted_path="pptxgallery.job_executor.execute_presentation_conversion",
        queue=LOCAL_QUEUE,
        upload_policy=PRESENTATION_POLICY,
        timeout_seconds=900,
    ),
    ExecutorMetadata(
        kind="teamcenter.set_properties",
        dotted_path="integrations.teamcenter.job_executor.execute_set_properties",
        queue=LOCAL_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=180,
    ),
    ExecutorMetadata(
        kind="doors.run_dxl",
        dotted_path="integrations.doors.runner_tasks.execute_dxl",
        queue=DOORS_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=120,
    ),
    ExecutorMetadata(
        kind="doors.update_object",
        dotted_path="integrations.doors.runner_tasks.update_object",
        queue=DOORS_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=120,
    ),
    ExecutorMetadata(
        kind="doors.create_object",
        dotted_path="integrations.doors.runner_tasks.create_object",
        queue=DOORS_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=120,
    ),
    ExecutorMetadata(
        kind="doors.link_requirements",
        dotted_path="integrations.doors.runner_tasks.link_requirements",
        queue=DOORS_QUEUE,
        upload_policy=JSON_OPERATION_POLICY,
        timeout_seconds=120,
    ),
)

_BY_KIND = {metadata.kind: metadata for metadata in EXECUTOR_CATALOG}
if len(_BY_KIND) != len(EXECUTOR_CATALOG):
    raise RuntimeError("Automation executor kinds must be unique.")
if any(metadata.queue not in SUPPORTED_QUEUES for metadata in EXECUTOR_CATALOG):
    raise RuntimeError("Automation executor queue is unsupported.")
if any(metadata.timeout_seconds < 1 for metadata in EXECUTOR_CATALOG):
    raise RuntimeError("Automation executor timeout must be positive.")


def executor_metadata(kind: str) -> ExecutorMetadata | None:
    """Return one allowlisted executor definition without importing its code."""

    return _BY_KIND.get(str(kind))


def executor_kinds(queue: str) -> tuple[str, ...]:
    """Return the immutable allowlist assigned to one execution queue."""

    if queue not in SUPPORTED_QUEUES:
        return ()
    return tuple(item.kind for item in EXECUTOR_CATALOG if item.queue == queue)
