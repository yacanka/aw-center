"""High-level bounded DOORS client."""

import tempfile
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from . import builder_link, builder_read, builder_write
from .builder_common import wrap_dxl
from .config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE, DoorsClientConfig
from .escape import decode_field
from .exceptions import DoorsDxlError, DoorsOperationError
from .models import DoorsObject, OperationResult
from .transport import DoorsOleTransport


class DoorsClient:
    """Expose bounded high-level IBM Rational DOORS operations."""

    def __init__(self, config: DoorsClientConfig, transport=None) -> None:
        self.config = config
        self.transport = transport or DoorsOleTransport(config)

    def connect(self) -> "DoorsClient":
        """Connect to the configured DOORS OLE client."""
        self.transport.connect()
        return self

    def run_dxl(self, body: str, result_mode: str | None = None) -> OperationResult:
        """Execute generated DXL using the requested result transport."""
        mode = result_mode or self.config.result_mode
        result_file = self.create_result_file(mode)
        try:
            script = wrap_dxl(body, result_file, mode)
            execution = self.transport.run_dxl(script, result_file, mode)
            errors = tuple(line for line in execution.lines if line.startswith("ERR\t"))
            return OperationResult(not errors, errors[0] if errors else "OK", execution.lines)
        finally:
            if result_file is not None:
                result_file.unlink(missing_ok=True)

    @staticmethod
    def create_result_file(result_mode: str) -> Path | None:
        """Create a unique file path only for file result mode."""
        if result_mode == RESULT_MODE_APPLICATION:
            return None
        if result_mode != RESULT_MODE_FILE:
            raise ValueError("Unsupported DOORS result mode.")
        return Path(tempfile.gettempdir()) / f"aw_doors_{uuid4().hex}.txt"

    def probe_application_result(self) -> OperationResult:
        """Verify a minimal oleSetResult to Application.Result round trip."""
        result = self.run_dxl('awc_ok("APPLICATION_RESULT_AVAILABLE")', RESULT_MODE_APPLICATION)
        self.raise_on_error(result)
        return result

    def check_module(self, module_path: str, mode: str = "read") -> OperationResult:
        """Check access to a DOORS module."""
        result = self.run_dxl(builder_read.check_module(module_path, mode))
        self.raise_on_error(result)
        return result

    def list_objects(self, module_path: str, attributes, loop: str, limit: int):
        """Return a bounded list of DOORS objects."""
        names = list(attributes)
        result = self.run_dxl(builder_read.list_objects(module_path, names, loop, limit))
        self.raise_on_error(result)
        return [self.parse_object(line, names) for line in result.raw_lines if line.startswith("OBJECT\t")]

    def export_module(self, module_path: str, limit: int):
        """Return bounded module columns and rows without accepting arbitrary DXL."""

        result = self.run_dxl(builder_read.export_module(module_path, limit))
        self.raise_on_error(result)
        columns = [
            decode_field(line.split("\t", 1)[1])
            for line in result.raw_lines
            if line.startswith("ATTRIBUTE\t")
        ]
        rows = [
            self.parse_object(line, columns).to_dict()
            for line in result.raw_lines
            if line.startswith("OBJECT\t")
        ]
        return {
            "columns": columns,
            "results": rows,
            "truncated": "TRUNCATED" in result.raw_lines,
            "attributes_truncated": "ATTRIBUTES_TRUNCATED" in result.raw_lines,
        }

    def get_object(self, module_path: str, absolute_number: int, attributes):
        """Return one DOORS object by absolute number."""
        names = list(attributes)
        result = self.run_dxl(builder_read.get_object(module_path, absolute_number, names))
        self.raise_on_error(result)
        for line in result.raw_lines:
            if line.startswith("OBJECT\t"):
                return self.parse_object(line, names)
        raise DoorsOperationError("DOORS did not return the requested object.")

    def set_object_attributes(self, module_path: str, absolute_number: int, attributes):
        """Update scalar attributes on one DOORS object."""
        result = self.run_dxl(
            builder_write.set_object_attributes(module_path, absolute_number, attributes)
        )
        self.raise_on_error(result)
        return result

    def create_object(self, module_path: str, position: str, relative_number, attributes):
        """Create one DOORS object in a module."""
        body = builder_write.create_object(module_path, position, relative_number, attributes)
        result = self.run_dxl(body)
        self.raise_on_error(result)
        for line in result.raw_lines:
            if line.startswith("CREATED\t"):
                return self.parse_created_object(line, attributes)
        raise DoorsOperationError("DOORS did not return the created object.")

    def link_requirements(self, values):
        """Preview or create the fixed Requirement PoC links."""

        result = self.run_dxl(builder_link.link_requirements(**values))
        self.raise_on_error(result)
        groups: dict[str, list[str]] = {}
        matched = set()
        missing = set()
        summary = {}
        for line in result.raw_lines:
            if line.startswith("GROUP\t"):
                _, key, requirement = line.split("\t", 2)
                groups.setdefault(decode_field(key) or "", []).append(
                    decode_field(requirement) or ""
                )
            elif line.startswith("TARGET\t"):
                matched.add(decode_field(line.split("\t", 1)[1]) or "")
            elif line.startswith("MISSING\t"):
                missing.add(decode_field(line.split("\t", 1)[1]) or "")
            elif line.startswith("SUMMARY\t"):
                summary = self.parse_link_summary(line)
        if not summary:
            raise DoorsDxlError("DOORS did not return the linker summary.")
        return {
            "type": "doors_requirement_linker",
            "schema_version": 1,
            "mode": "link" if values["activeness"] else "preview",
            "direction": values["direction"],
            "summary": summary,
            "groups": [
                {
                    "poc": key,
                    "requirements": requirements,
                    "target_found": key in matched,
                }
                for key, requirements in groups.items()
            ],
            "missing_targets": sorted(missing),
        }

    @staticmethod
    def parse_link_summary(line: str) -> dict[str, int]:
        """Parse the fixed bounded Linker summary row."""

        values = line.split("\t")[1:]
        if len(values) != 7:
            raise DoorsDxlError("DOORS returned a malformed linker summary.")
        try:
            counts = [int(value) for value in values]
        except ValueError as error:
            raise DoorsDxlError("DOORS returned a malformed linker summary.") from error
        return dict(
            zip(
                (
                    "reference_objects",
                    "groups",
                    "candidates",
                    "matched_targets",
                    "missing_targets",
                    "created_links",
                    "existing_links",
                ),
                counts,
            )
        )
    
    def get_attr(self, module_path: str, search_text: str):
        """Create one DOORS object in a module."""
        body = builder_read.get_attr(module_path, search_text)
        result = self.run_dxl(body)
        self.raise_on_error(result)
        for line in result.raw_lines:
            if line.startswith("OBJECT\t"):
                return self.parse_info(line)
        raise DoorsOperationError("DOORS did not return the object.")

    
    def check_applicable_disciplines(self, module_path: str):
        """Return the bounded attributes used by the discipline check."""
        applicable_attr = self.get_attr(module_path, "Applicable")
        discipline_attr = self.get_attr(module_path, "Discipline")
        return self.list_objects(
            module_path,
            [applicable_attr, discipline_attr],
            "entire",
            20,
        )

    @staticmethod
    def parse_info(line: str) -> str:
        """Parse one line-oriented DOORS object result."""
        try:
            return decode_field(line.split("\t")[1])
        except ValueError:
            raise DoorsDxlError("DOORS returned a malformed info.") 

    @staticmethod
    def parse_object(line: str, attributes: Iterable[str]) -> DoorsObject:
        """Parse one line-oriented DOORS object result."""
        values = [decode_field(part) for part in line.split("\t")[1:]]
        if len(values) < 3:
            raise DoorsDxlError("DOORS returned a malformed object row.")
        attribute_values = dict(zip(attributes, values[3:]))
        level = int(values[2]) if values[2] not in {None, ""} else None
        return DoorsObject(int(values[0]), values[1] or "", level, attribute_values)

    @staticmethod
    def parse_created_object(line: str, attributes: dict) -> DoorsObject:
        """Parse one line-oriented created-object result."""
        values = [decode_field(part) for part in line.split("\t")[1:]]
        if len(values) < 3:
            raise DoorsDxlError("DOORS returned a malformed created-object row.")
        level = int(values[2]) if values[2] not in {None, ""} else None
        return DoorsObject(int(values[0]), values[1] or "", level, attributes)

    @staticmethod
    def raise_on_error(result: OperationResult) -> None:
        """Raise an operation error containing the DXL code and reason."""
        if result.ok:
            return
        _, code, detail = (result.message.split("\t", 2) + ["", ""])[:3]
        decoded_code = decode_field(code or "DXL_ERROR") or "DXL_ERROR"
        decoded_detail = decode_field(detail or "") or "No additional detail was returned."
        raise DoorsOperationError(
            f"DOORS operation failed ({decoded_code}): {decoded_detail}", code=decoded_code
        )
