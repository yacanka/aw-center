import json
from pathlib import Path

from django.conf import settings

from jobs.artifacts import materialize_job_input, temporary_output
from jobs.contracts import JobExecutionFailure, JobExecutionResult
from jobs.worker import update_progress
from word.analysis_contracts import ANALYSIS_CHECKS, validate_check_ids
from word.analysis_results import bounded_index, bounded_score, score_status
from word.service.paraphrase import ExplainableDocxRetriever


def execute_document_analysis(job):
    """Analyze a Word document and produce a private explainable JSON report."""

    check_ids = validate_check_ids(job.parameters.get("check_ids"))
    input_path = materialize_job_input(job)
    output_path = temporary_output(".json")
    result_ready = False
    try:
        report, summary = analyze_document(job.id, input_path, job.input_name, check_ids)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        result_ready = True
        filename = f"analysis-{Path(job.input_name).stem[:100]}.json"
        return JobExecutionResult(output_path, filename, "Document analysis completed.", summary)
    finally:
        input_path.unlink(missing_ok=True)
        if not result_ready:
            output_path.unlink(missing_ok=True)


def analyze_document(job_id, input_path, input_name, check_ids):
    """Build one local semantic index and execute allowlisted checks."""

    engine = create_analysis_engine()
    update_progress(job_id, 10, "Extracting document structure.")
    add_document(engine, input_path, input_name)
    update_progress(job_id, 25, "Building private semantic index.")
    build_analysis_index(engine)
    results = execute_checks(job_id, engine, check_ids)
    return {"document": input_name, "checks": results}, summarize_results(results)


def create_analysis_engine():
    """Create the configured local explainable retrieval engine."""

    try:
        return ExplainableDocxRetriever(
            model_path=str(settings.WORD_ANALYZER_BI_MODEL),
            cross_encoder_model=str(settings.WORD_ANALYZER_CROSS_MODEL),
            content_mode="both",
            use_heading_weight=True,
        )
    except Exception as error:
        raise JobExecutionFailure(
            "The configured document analysis models are unavailable.",
            "WORD_ANALYZER_MODEL_UNAVAILABLE",
            True,
        ) from error


def build_analysis_index(engine):
    """Build the local index behind a sanitized failure boundary."""

    try:
        engine.build_index()
    except Exception as error:
        raise JobExecutionFailure(
            "The private semantic index could not be built.",
            "WORD_ANALYZER_EXECUTION_FAILED",
            True,
        ) from error


def add_document(engine, input_path, input_name):
    """Extract bounded semantic units from one validated document."""

    try:
        with input_path.open("rb") as source:
            engine.add_docx_file(source, input_name)
    except Exception as error:
        raise JobExecutionFailure("The Word document could not be analyzed.", "WORD_ANALYZER_INVALID") from error
    if not engine.units:
        raise JobExecutionFailure("No analyzable document text was found.", "WORD_ANALYZER_EMPTY")
    if len(engine.units) > settings.WORD_ANALYZER_MAX_UNITS:
        raise JobExecutionFailure("The document exceeds the analysis unit limit.", "WORD_ANALYZER_UNIT_LIMIT")


def execute_checks(job_id, engine, check_ids):
    """Run allowlisted checks and publish bounded progress between searches."""

    results = []
    total = len(check_ids)
    for index, check_id in enumerate(check_ids, start=1):
        progress = 30 + int((index - 1) / total * 60)
        update_progress(job_id, progress, f"Running analysis check {index}/{total}.")
        result = search_engine(engine, ANALYSIS_CHECKS[check_id])
        results.append(sanitize_result(check_id, result))
    return results


def search_engine(engine, query):
    """Run one local model search behind a sanitized failure boundary."""

    try:
        return engine.search(query)
    except Exception as error:
        raise JobExecutionFailure(
            "The private document analysis could not be completed.",
            "WORD_ANALYZER_EXECUTION_FAILED",
            True,
        ) from error


def sanitize_result(check_id, result):
    """Keep explainable evidence while removing internal paths and model objects."""

    evidence = [sanitize_evidence(item) for item in result.get("results", [])[:5]]
    score = bounded_score(result.get("best_score"))
    return {
        "id": check_id,
        "title": ANALYSIS_CHECKS[check_id],
        "score": score,
        "status": score_status(score),
        "explanation": str(result.get("explanation", ""))[:4000],
        "evidence": evidence,
    }


def sanitize_evidence(item):
    """Return an allowlisted evidence record for the private report."""

    metadata = item.get("metadata", {})
    source_type = metadata.get("source_type")
    heading = metadata.get("heading")
    return {
        "text": str(item.get("text", ""))[:1200],
        "score": bounded_score(item.get("final_score")),
        "source_type": source_type if source_type in {"paragraph", "table"} else "unknown",
        "heading": str(heading)[:300] if heading else None,
        "paragraph_index": bounded_index(metadata.get("paragraph_index")),
        "table_index": bounded_index(metadata.get("table_index")),
        "row_index": bounded_index(metadata.get("row_index")),
    }


def summarize_results(results):
    """Create a content-free Job Center summary from private analysis results."""

    checks = [
        {"id": item["id"], "title": item["title"], "score": item["score"], "status": item["status"]}
        for item in results
    ]
    overall = round(sum(item["score"] for item in results) / max(1, len(results)), 6)
    return {
        "type": "document_analysis",
        "overall_score": overall,
        "passed": sum(item["status"] == "success" for item in results),
        "total": len(results),
        "checks": checks,
    }
