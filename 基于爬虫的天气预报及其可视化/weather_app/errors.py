"""统一异常类型。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """带有稳定错误码和 HTTP 状态码的业务异常。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "BAD_REQUEST",
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class CityNotFoundError(ApiError):
    def __init__(self, message: str, *, suggestions: list[dict] | None = None) -> None:
        super().__init__(
            message,
            code="CITY_NOT_FOUND",
            status_code=404,
            details={"suggestions": suggestions or []},
        )


class UpstreamError(ApiError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(
            message,
            code="UPSTREAM_UNAVAILABLE",
            status_code=502,
            details=details,
        )


class QueueBusyError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            "当前查询人数较多，请稍后重试",
            code="QUEUE_BUSY",
            status_code=503,
        )
