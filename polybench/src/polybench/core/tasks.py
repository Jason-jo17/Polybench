"""Choosing tasks for a run, and describing them without their hidden parts."""

from pathlib import Path
from typing import Any

from polybench.schemas import Difficulty, Task
from polybench.tasks.loader import load_tasks
from polybench.tasks.registry import TaskRegistry


def parse_tags(tags: str | list[str] | None) -> list[str] | None:
    """Accept tags as a list or a comma-separated string; None when there are none."""
    if not tags:
        return None
    items = tags.split(",") if isinstance(tags, str) else tags
    cleaned = [t.strip() for t in items if t.strip()]
    return cleaned or None


def select_tasks(
    tasks_dir: str | Path,
    lang: str | None = None,
    difficulty: Difficulty | str | None = None,
    tags: list[str] | None = None,
) -> list[Task]:
    """Load every task under `tasks_dir` and keep those matching all the filters.

    Raises ValueError for an unknown difficulty, and for a malformed task file.
    """
    level = Difficulty(difficulty) if difficulty else None
    return TaskRegistry(load_tasks(tasks_dir)).filter(
        lang=lang or None, difficulty=level, tags=tags
    )


def find_task(tasks_dir: str | Path, task_id: str) -> Task | None:
    return next((t for t in load_tasks(tasks_dir) if t.id == task_id), None)


def public_task(task: Task, *, detail: bool = True) -> dict[str, Any]:
    """A task as it may be shown to users and agents.

    Never includes `test_code` or `reference_solution`: exposing the hidden tests
    would let a model be tuned to them. `detail=False` gives the short listing form.
    """
    out: dict[str, Any] = {
        "id": task.id,
        "language": task.language,
        "difficulty": task.difficulty.value,
        "tags": task.tags,
    }
    if detail:
        out |= {
            "title": task.title,
            "prompt": task.prompt,
            "signature": task.signature,
            "timeout_seconds": task.timeout_seconds,
        }
    return out
