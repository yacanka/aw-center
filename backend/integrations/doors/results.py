"""Versioned DOORS result metadata alongside the existing output fields.

Inputs and outputs stay in the owner-only artifact. Only fixed messages are
copied to the job record; raw DXL diagnostics never become public messages.
"""


SUCCESS_RESULTS = {
    "check_module_quality": ("MODULE_QUALITY_DONE", "Quality check completed. Review the quality report for findings and coverage."),
    "check_module": ("MODULE_OPENED", "Module found and readable."),
    "get_object": ("OBJECT_READ", "Object read successfully."),
    "list_objects": ("LIST_OBJECTS_DONE", "Module objects read successfully."),
    "export_module": ("EXPORT_MODULE_DONE", "Module export completed."),
    "check_applicable_disciplines": ("DISCIPLINE_CHECK_DONE", "Discipline check completed."),
    "update_object": ("ATTRIBUTES_SAVED", "Object attributes saved."),
    "create_object": ("OBJECT_CREATED", "Object created and saved."),
    "link_requirements": ("REQUIREMENT_LINKER_DONE", "Requirement link operation completed."),
}


def operation_result(operation, inputs, output):
    """Add stable metadata without moving or duplicating existing output rows."""
    code, message = SUCCESS_RESULTS[operation]
    outcome = "success"
    if operation == "check_module" and output["accessible"] is False:
        outcome = "negative"
        code = "OPEN_MODULE"
        message = "Module not found or no read access. Check the module path and read permission."
    return {
        **output,
        "operation_result": {
            "schema_version": 1,
            "operation": operation,
            "outcome": outcome,
            "code": code,
            "message": message,
            "input": dict(inputs),
        },
    }
