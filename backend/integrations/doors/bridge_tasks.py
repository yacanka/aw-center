"""Windows-agent DOORS callables using only artifact payloads and the OLE client."""

import json
from pathlib import Path

from automations.catalog import JSON_OPERATION_POLICY

from .serializers import (
    ModuleSerializer,
    ModuleExportSerializer,
    ObjectCreateSerializer,
    ObjectDetailSerializer,
    ObjectListSerializer,
    ObjectUpdateSerializer,
    RequirementLinkSerializer,
)
from .services import execute_with_client

MAX_RESULT_BYTES = 10 * 1024 * 1024
READ_OPERATIONS = frozenset(
    {
        "check_applicable_disciplines",
        "check_module",
        "get_object",
        "list_objects",
        "export_module",
    }
)


class BridgeTaskPayloadError(ValueError):
    """Reject an invalid or unsupported Windows automation artifact."""


def execute_dxl(input_path, output_path):
    """Execute one explicitly allowlisted read operation and write JSON output."""

    payload = load_payload(input_path)
    operation = payload.get("operation")
    if operation not in READ_OPERATIONS:
        raise BridgeTaskPayloadError("Unsupported DOORS read operation.")
    if operation == "check_module":
        values = validated(ModuleSerializer, payload)
        result = execute_with_client(
            lambda client: {
                "accessible": client.check_module(values["module_path"]).ok,
                "module_path": values["module_path"],
            }
        )
    elif operation == "export_module":
        values = validated(ModuleExportSerializer, payload)
        exported = execute_with_client(
            lambda client: client.export_module(values["module_path"], values["limit"])
        )
        result = {
            "type": "doors_module_export",
            "schema_version": 1,
            "module_path": values["module_path"],
            "columns": exported["columns"],
            "count": len(exported["results"]),
            "results": exported["results"],
            "truncated": exported["truncated"],
            "attributes_truncated": exported["attributes_truncated"],
        }
    elif operation == "check_applicable_disciplines":
        values = validated(ModuleSerializer, payload)
        objects = execute_with_client(
            lambda client: client.check_applicable_disciplines(values["module_path"])
        )
        result = {
            "count": len(objects),
            "results": [item.to_dict() for item in objects],
        }
    elif operation == "get_object":
        values = validated(ObjectDetailSerializer, payload)
        result = execute_with_client(
            lambda client: client.get_object(
                values["module_path"],
                values["absolute_number"],
                values["attributes"],
            ).to_dict()
        )
    else:
        values = validated(ObjectListSerializer, payload)
        result = execute_with_client(
            lambda client: {
                "results": [
                    item.to_dict()
                    for item in client.list_objects(
                        values["module_path"],
                        values["attributes"],
                        values["loop"],
                        values["limit"],
                    )
                ]
            }
        )
        result["count"] = len(result["results"])
    return write_result(output_path, result)


def update_object(input_path, output_path):
    """Execute one validated object update; arbitrary DXL is never accepted."""

    values = validated(ObjectUpdateSerializer, load_payload(input_path))
    execute_with_client(
        lambda client: client.set_object_attributes(
            values["module_path"], values["absolute_number"], values["attributes"]
        )
    )
    return write_result(
        output_path,
        {"updated": True, "absolute_number": values["absolute_number"]},
    )


def create_object(input_path, output_path):
    """Execute one validated object creation and emit its bounded representation."""

    values = validated(ObjectCreateSerializer, load_payload(input_path))
    created = execute_with_client(
        lambda client: client.create_object(
            values["module_path"],
            values["position"],
            values.get("relative_absolute_number"),
            values["attributes"],
        )
    )
    return write_result(output_path, created.to_dict())


def link_requirements(input_path, output_path):
    """Execute only the validated fixed-purpose Requirement PoC Linker."""

    values = validated(RequirementLinkSerializer, load_payload(input_path))
    result = execute_with_client(lambda client: client.link_requirements(dict(values)))
    return write_result(output_path, result)


def load_payload(input_path):
    """Load one bounded JSON object from the execution-scoped input artifact."""

    path = Path(input_path)
    try:
        size = path.stat().st_size
        if size < 2 or size > JSON_OPERATION_POLICY.maximum_bytes:
            raise BridgeTaskPayloadError("DOORS automation payload size is invalid.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BridgeTaskPayloadError("DOORS automation payload is invalid.") from error
    if not isinstance(payload, dict):
        raise BridgeTaskPayloadError("DOORS automation payload must be an object.")
    return payload


def validated(serializer_class, payload):
    """Apply the existing operation-specific serializer contract to an artifact."""

    values = {key: value for key, value in payload.items() if key != "operation"}
    serializer = serializer_class(data=values)
    if set(values) - set(serializer.fields) or not serializer.is_valid():
        raise BridgeTaskPayloadError("DOORS automation payload failed validation.")
    return serializer.validated_data


def write_result(output_path, payload):
    """Write a deterministic JSON artifact and return content-free metadata."""

    path = Path(output_path)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not encoded or len(encoded) > MAX_RESULT_BYTES:
        raise BridgeTaskPayloadError("DOORS automation result exceeds the safety limit.")
    path.write_bytes(encoded)
    return {
        "filename": "doors-result.json",
        "sha256_required": True,
        "bytes": len(encoded),
    }
