from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sos.models import WriteOperation


@dataclass(frozen=True)
class ArchiveMove:
    source: Path
    target: Path


def execute_move_to_archive(
    operation: WriteOperation,
    journal: list[ArchiveMove],
) -> None:
    source = operation.source
    target = operation.target
    if source is None or target is None:
        raise ValueError("archive operation requires source and target")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
    except OSError:
        shutil.copytree(source, target)
        shutil.rmtree(source)
    journal.append(ArchiveMove(source=source, target=target))


def rollback_archive_moves(journal: tuple[ArchiveMove, ...]) -> None:
    for move in reversed(journal):
        if not move.target.exists():
            continue
        if move.source.exists():
            if move.source.is_dir():
                shutil.rmtree(move.source)
            else:
                move.source.unlink()
        move.source.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(move.target, move.source)
        except OSError:
            shutil.copytree(move.target, move.source)
            shutil.rmtree(move.target)
