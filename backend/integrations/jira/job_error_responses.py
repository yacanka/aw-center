"""Sanitized HTTP responses for DCC preview failures."""

from awcenter.api_errors import error_response


def jira_unavailable_response():
    """Return the sanitized transient JIRA transport failure."""

    return error_response(
        "JIRA could not authenticate or read the task.",
        code="DCC_JIRA_UNAVAILABLE", response_status=502,
    )


def unexpected_capture_response(logger):
    """Log an unexpected capture failure and return a safe response."""

    logger.exception("DCC preview capture failed")
    return error_response(
        "The DCC source could not be previewed.", code="DCC_CAPTURE_FAILED",
        response_status=502,
    )


def snapshot_error_response(error):
    """Map a safe snapshot failure to its intended HTTP status."""

    return error_response(
        str(error), code=error.code, response_status=error.response_status
    )
