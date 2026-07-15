import tempfile
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from . import builder_read, builder_write
from .builder_common import wrap_dxl
from .config import DoorsClientConfig
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

    def run_dxl(self, body: str) -> OperationResult:
        """Execute generated DXL and always clean its temporary result."""
        result_file = Path(tempfile.gettempdir()) / f"aw_doors_{uuid4().hex}.txt"
        try:
            execution = self.transport.run_dxl(wrap_dxl(body, result_file), result_file)
            errors = tuple(line for line in execution.lines if line.startswith("ERR\t"))
            return OperationResult(not errors, errors[0] if errors else "OK", execution.lines)
        finally:
            result_file.unlink(missing_ok=True)

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
        """Raise a sanitized operation error for DXL ERR rows."""
        if result.ok:
            return
        code = result.message.split("\t", 2)[1] if "\t" in result.message else "DXL_ERROR"
        raise DoorsOperationError(f"DOORS operation failed with code {decode_field(code)}.")
