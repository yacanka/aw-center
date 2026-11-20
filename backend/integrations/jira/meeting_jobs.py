"""Convert private minutes into the bounded input for the JIRA review workflow."""

import json

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult

from .meeting_minutes import MinutesParseError, parse_minutes_document
from .subtask_serializers import MAX_SUBTASKS_PER_BATCH

MEETING_JOB_KIND = "jira.read_meeting_minutes"
MEETING_FIELDS = {
    "project": "Proje", "subject": "Konu", "mom_no": "Tutanak No", "revision": "Revizyon",
    "date_time": "Tarih / Saat", "location": "Toplantı Yeri", "agenda": "Gündem",
    "discussions_decisions": "Görüşmeler ve kararlar",
}


def minutes_report(data):
    description = "\n\n".join(
        f"{label}\n{data[key]}" for key, label in MEETING_FIELDS.items() if data[key]
    )
    actions = data["action_items"]
    if not description or not (data["subject"] or data["mom_no"] or data["action_item_list_found"]):
        raise MinutesParseError("The document does not contain recognized meeting minutes.")
    summary = data["subject"] or f"Toplantı tutanağı {data['mom_no']}".strip()
    report = {"summary": summary, "description": description, "actions": actions}
    if len(summary) > 255 or len(description) > 30000 or len(actions) > MAX_SUBTASKS_PER_BATCH:
        raise MinutesParseError("The minutes exceed the JIRA title, description or action limits.")
    return report


def execute_meeting_minutes(job):
    source = materialize_job_input(job)
    try:
        report = minutes_report(parse_minutes_document(source))
        payload = json.dumps(report, ensure_ascii=False).encode("utf-8")
        if len(payload) > 1024 * 1024:
            raise MinutesParseError("The meeting report exceeds the size limit.")
    except MinutesParseError as error:
        raise JobExecutionFailure(str(error), "MEETING_MINUTES_INVALID") from error
    except Exception as error:
        raise JobExecutionFailure("The Word document could not be read.", "MEETING_MINUTES_INVALID") from error
    finally:
        source.unlink(missing_ok=True)
    output = temporary_output(".json")
    try:
        output.write_bytes(payload)
        return JobExecutionResult(output, "meeting-minutes.json", "Meeting minutes ready for review.")
    except OSError:
        output.unlink(missing_ok=True)
        raise
