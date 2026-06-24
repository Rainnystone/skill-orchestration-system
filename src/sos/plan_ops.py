"""Shared plan operation helpers.

Consolidates ``operations_of_kind`` and ``single_operation`` that were
duplicated across apply.py, sync.py, and cli.py.
"""

from __future__ import annotations

from typing import Protocol

from sos.models import OperationKind, WriteOperation


class _HasOperations(Protocol):
    operations: tuple[WriteOperation, ...]


def operations_of_kind(
    plan: _HasOperations,
    kind: OperationKind,
) -> tuple[WriteOperation, ...]:
    """Return all operations of *kind* from *plan*, preserving order."""
    return tuple(operation for operation in plan.operations if operation.kind == kind)


def single_operation(
    plan: _HasOperations,
    kind: OperationKind,
) -> WriteOperation:
    """Return the single operation of *kind* from *plan*.

    Raises ValueError if there is not exactly one such operation.
    """
    operations = operations_of_kind(plan, kind)
    if len(operations) != 1:
        raise ValueError(f"expected exactly one {kind.value} operation, found {len(operations)}")
    return operations[0]
