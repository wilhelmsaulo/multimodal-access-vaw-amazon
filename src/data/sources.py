"""Reused with adaptation from https://github.com/wilhelmsaulo/explainable-municipal-prioritization-framework/blob/main/src/empriority/data_sources.py (blob 5863360afcdd8e9de259e4bc778e9967fc980657).
Authorized by the repository owner for this project; provenance retained pending final licensing audit.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class DataSourceError(RuntimeError):
    """Base error raised by the data-source registry."""


class DataSourceAlreadyRegisteredError(DataSourceError):
    """Raised when an operation name is registered more than once."""


class DataSourceNotFoundError(DataSourceError):
    """Raised when an unknown operation is requested."""


@dataclass(frozen=True)
class DataSourceOperation(Generic[T]):
    """Named callable exposed by one official data source."""

    name: str
    handler: Callable[..., T]
    description: str = ""

    def execute(self, *args: Any, **kwargs: Any) -> T:
        return self.handler(*args, **kwargs)


class DataSourceManager:
    """Registry and execution facade for heterogeneous official data sources.

    The manager knows operation names and callables, but does not depend on API,
    FTP or file-transfer details. Connectors remain responsible for source-
    specific communication and normalization.
    """

    def __init__(self, operations: Iterable[DataSourceOperation[Any]] | None = None) -> None:
        self._operations: dict[str, DataSourceOperation[Any]] = {}
        for operation in operations or ():
            self.register(operation)

    def register(self, operation: DataSourceOperation[Any]) -> None:
        name = self._normalize_name(operation.name)
        if name in self._operations:
            raise DataSourceAlreadyRegisteredError(
                f"Data-source operation already registered: {name}"
            )
        self._operations[name] = DataSourceOperation(
            name=name,
            handler=operation.handler,
            description=operation.description,
        )

    def register_handler(
        self,
        name: str,
        handler: Callable[..., T],
        *,
        description: str = "",
    ) -> None:
        self.register(DataSourceOperation(name=name, handler=handler, description=description))

    def run(self, name: str, *args: Any, **kwargs: Any) -> Any:
        normalized_name = self._normalize_name(name)
        try:
            operation = self._operations[normalized_name]
        except KeyError as exc:
            available = ", ".join(self.names()) or "none"
            raise DataSourceNotFoundError(
                f"Unknown data-source operation '{normalized_name}'. Available: {available}"
            ) from exc
        return operation.execute(*args, **kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def describe(self) -> dict[str, str]:
        return {name: self._operations[name].description for name in self.names()}

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self._normalize_name(name) in self._operations

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Data-source operation name cannot be empty.")
        return normalized
