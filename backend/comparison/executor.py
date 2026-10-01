"""Local executors publish only through the existing fenced job worker."""

from dataclasses import asdict
import json
import time

from jobs.artifacts import materialize_job_input, temporary_output, remove_temporary_artifact
from jobs.contracts import JobExecutionFailure, JobExecutionResult, JobCancelled, JobLeaseLost
from jobs.execution import update_progress, cancellation_requested

from .contracts import CompareError, ComparisonResult, resolve_options
from .excel import inspect_excel, compare_excel
from .matching import compare_text
from .packaging import read_package
from .readers import read_document
from .reports import write_report


class Checkpoint:
    """Check cancellation periodically without a database query for every row."""

    def __init__(self, job):
        self.job = job
        self.last_check = 0

    def __call__(self):
        now = time.monotonic()
        if now - self.last_check >= .25:
            self.last_check = now
            if cancellation_requested(self.job.id):
                raise JobCancelled()


def execute_inspection(job):
    return execute(job, inspection=True)


def execute_comparison(job):
    return execute(job, inspection=False)


def execute(job, *, inspection):
    input_path = None
    output_path = None
    completed = False
    checkpoint = Checkpoint(job)
    try:
        input_path = materialize_job_input(job)
        update_progress(job.id, 5, 'Validating comparison input.')
        family, contents = read_package(input_path)
        options = resolve_options(job.parameters.get('options', {}), family)
        selection = job.parameters.get('selection', {})
        checkpoint()
        update_progress(job.id, 15, 'Reading and matching content.')
        if inspection:
            if family != 'excel':
                raise CompareError('Table inspection requires Excel workbooks.')
            data = inspect_excel(*contents, selection, options, checkpoint)
            data['options'] = asdict(options)
            output_path = temporary_output('.json')
            output_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            result = JobExecutionResult(output_path, 'comparison-inspection.json', 'Table inspection ready.',
                                       {'requires_input': data['matching']['requires_input']})
        else:
            result = render_comparison(job, family, contents, selection, options, checkpoint)
            output_path = result.path
        checkpoint()
        completed = True
        return result
    except CompareError as error:
        raise JobExecutionFailure(error.detail, error.code) from error
    except (JobCancelled, JobLeaseLost, JobExecutionFailure):
        raise
    except Exception as error:
        raise JobExecutionFailure('The supplied files could not be compared. Check that they are readable and supported.',
                                  'COMPARE_FAILED') from error
    finally:
        if input_path:
            remove_temporary_artifact(input_path)
        if output_path and not completed:
            remove_temporary_artifact(output_path)


def render_comparison(job, family, contents, selection, options, checkpoint):
    if family == 'excel':
        result = compare_excel(*contents, selection, options, checkpoint)
    else:
        old, old_warnings = read_document(contents[0], family, checkpoint)
        new, new_warnings = read_document(contents[1], family, checkpoint)
        result = ComparisonResult(family, options, compare_text(old, new, options, checkpoint), 'text',
                                  [f'Old: {item}' for item in old_warnings] + [f'New: {item}' for item in new_warnings])
    update_progress(job.id, 75, 'Writing comparison report.')
    extension = '.xlsx' if options.output_type == 'excel' else '.docx'
    path = temporary_output(extension)
    try:
        write_report(result, path, checkpoint)
        return JobExecutionResult(path, 'Comparison Result' + extension, 'Comparison report ready.',
                                  {**result.counts, 'format': family, 'output_type': options.output_type})
    except BaseException:
        remove_temporary_artifact(path)
        raise
