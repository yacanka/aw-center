"""Project-specific controls applied before DCC subtask rendering."""

from typing import Any, Callable, Mapping, Sequence

from projects.gokbey.dcc_subtasks import control_jandarma_subtasks

from .subtask_control_contract import SubtaskControlResult


SubtaskControl = Callable[[tuple[Any, ...]], SubtaskControlResult]

# Keep business rules in their project package; this registry is the integration boundary.
PROJECT_SUBTASK_CONTROLS: dict[str, SubtaskControl] = {
    "gokbey": control_jandarma_subtasks,
}


def apply_project_subtask_control(
    project_slug: str, subtasks: Sequence[Any]
) -> SubtaskControlResult:
    """Apply a registered project algorithm or preserve the source subtasks."""

    source_subtasks = tuple(subtasks)
    control = PROJECT_SUBTASK_CONTROLS.get(project_slug)
    result = control(source_subtasks) if control else SubtaskControlResult(source_subtasks)
    validate_control_result(result)
    return result


def validate_control_result(result: SubtaskControlResult) -> None:
    """Reject malformed project results before they enter a document snapshot."""

    if not isinstance(result, SubtaskControlResult):
        raise TypeError("DCC subtask controls must return SubtaskControlResult.")
    if not isinstance(result.subtasks, tuple):
        raise TypeError("Controlled DCC subtasks must be returned as a tuple.")
    if not isinstance(result.render_context, Mapping):
        raise TypeError("DCC project render context must be a mapping.")
    if any(not isinstance(key, str) for key in result.render_context):
        raise TypeError("DCC project render context keys must be strings.")
    if not isinstance(result.placeholder_overrides, Mapping):
        raise TypeError("DCC placeholder overrides must be a mapping.")
    invalid_pair = any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in result.placeholder_overrides.items()
    )
    if invalid_pair:
        raise TypeError("DCC placeholder overrides must contain string pairs.")
