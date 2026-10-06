"""Immutable server-owned contracts for stateless AI service calls."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class AIRequestPolicy:
    purpose: str
    max_request_bytes: int
    max_response_bytes: int
    connect_timeout: float
    read_timeout: float


@dataclass(frozen=True)
class AIConfiguration:
    url: str
    model: str
    token: str = field(repr=False)
    allowed_hosts: tuple[str, ...]
    connect_timeout: float
    read_timeout: float
    max_response_bytes: int


class AIServiceError(RuntimeError):
    """Expose only a safe detail, stable AI code and suggested HTTP status."""

    def __init__(self, detail: str, code: str, response_status: int):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.response_status = response_status
