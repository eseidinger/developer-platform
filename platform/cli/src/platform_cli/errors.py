"""Safe API error mapping and stable command exit codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiError(Exception):
    status_code: int
    detail: str
    code: str | None = None
    request_id: str | None = None

    @property
    def exit_code(self) -> int:
        return exit_code_for_status(self.status_code)


def exit_code_for_status(status_code: int) -> int:
    if status_code in {401}:
        return 3
    if status_code == 403:
        return 4
    if status_code == 404:
        return 5
    if status_code == 409:
        return 6
    if status_code in {400, 422}:
        return 7
    if status_code == 429 or status_code >= 500:
        return 8
    return 8


def safe_error_body(value: Any) -> tuple[str, str | None]:
    if not isinstance(value, dict):
        return "The platform returned an error without a safe detail.", None
    detail = value.get("detail")
    code = value.get("code")
    return (
        detail if isinstance(detail, str) else "The platform returned an error without a safe detail.",
        code if isinstance(code, str) else None,
    )
