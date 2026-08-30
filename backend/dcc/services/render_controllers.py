"""Project-specific data controls applied immediately before DCC rendering."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from projects.policies.gokbey import control_gokbey_dcc
from projects.registry import GOKBEY_DCC_CONTROLLER, get_project_definition


DccRenderController = Callable[[dict[str, Any]], Mapping[str, Any]]

# Controller implementations are statically allowlisted. Project selection remains
# technical, read-only metadata in the central project registry.
CONTROLLERS: dict[str, DccRenderController] = {
    GOKBEY_DCC_CONTROLLER: control_gokbey_dcc,
}


def apply_project_dcc_controller(
    project_slug: str, render_context: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply project rules to an isolated context, including panel reshaping."""

    if not isinstance(render_context, Mapping):
        raise TypeError("DCC render context must be a mapping.")
    controlled_context = deepcopy(dict(render_context))
    definition = get_project_definition(project_slug)
    controller_key = definition.dcc_controller
    if not controller_key:
        return controlled_context
    controller = CONTROLLERS.get(controller_key)
    if controller is None:
        raise RuntimeError(f"Project DCC controller is not installed: {controller_key}")
    result = controller(controlled_context)
    validate_controller_result(result)
    return dict(result)


def validate_controller_result(result: object) -> None:
    """Reject malformed controller results before passing them to docxtpl."""

    if not isinstance(result, Mapping):
        raise TypeError("Project DCC controllers must return a mapping.")
    if any(not isinstance(key, str) for key in result):
        raise TypeError("Project DCC controller keys must be strings.")
    panels = result.get("Panels")
    if panels is not None and not isinstance(panels, list):
        raise TypeError("Project DCC controllers must preserve Panels as a list.")
    if panels is not None and any(not isinstance(panel, Mapping) for panel in panels):
        raise TypeError("Project DCC controller Panels entries must be mappings.")
    if panels is not None and any(
        not isinstance(key, str) for panel in panels for key in panel
    ):
        raise TypeError("Project DCC controller panel keys must be strings.")
