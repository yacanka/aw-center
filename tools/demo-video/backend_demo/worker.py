"""Run the ordinary durable worker state machine using recording-only adapters."""
import time
from docx import Document
from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionResult, JobExecutionFailure, JobCancelled
from jobs.execution import update_progress, cancellation_requested
from examples import TEXT


def translation(job):
    from jobs.kind_contracts import WORD_TRANSLATION_LABELS
    from pathlib import Path
    direction = job.parameters['translate_type']
    dictionary = TEXT if direction == 'tr2en' else {v:k for k,v in TEXT.items()}
    source = materialize_job_input(job)
    try:
        doc = Document(source)
        for progress, message in [(12, 'Belge metni okunuyor.'), (42, 'Örnek paragraflar eşleştiriliyor.'), (78, 'Çevrilen paragraflar belgeye yazılıyor.')]:
            update_progress(job.id, progress, message)
            for _ in range(12):
                if cancellation_requested(job.id):
                    raise JobCancelled()
                time.sleep(.2)
        for p in doc.paragraphs:
            if not p.text.strip():
                continue
            if p.text not in dictionary:
                raise JobExecutionFailure('Bu örnek sözlükte yer almayan metin bulundu.', 'DEMO_TRANSLATION_UNAVAILABLE')
            p.text = dictionary[p.text]
        output = temporary_output('.docx')
        doc.save(output)
        return JobExecutionResult(output, f'[{WORD_TRANSLATION_LABELS[direction]}] {Path(job.input_name).stem}.docx', 'Çeviri belgesi hazır.')
    finally:
        source.unlink(missing_ok=True)


def executor(kind):
    if kind == 'word.translate':
        return translation
    import importlib.util
    if importlib.util.find_spec('local_adapters'):
        resolve = getattr(__import__('local_adapters'), 'resolve', lambda k: None)
        handler = resolve(kind)
        if handler:
            return handler
    from awcenter.job_executors import resolve_worker_executor
    return resolve_worker_executor(kind)


def work(stop):
    from django.db import connections, close_old_connections
    from jobs.execution import remove_worker
    from jobs.worker import claim_next_job, execute_claimed_job
    worker = 'doors-worker:atlas-demo'
    try:
        while not stop.is_set():
            close_old_connections()
            job = claim_next_job(worker)
            if job:
                execute_claimed_job(job, executor)
            stop.wait(.3)
    finally:
        remove_worker(worker)
        connections.close_all()
