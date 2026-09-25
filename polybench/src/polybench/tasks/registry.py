from collections.abc import Iterable
from typing import Optional

from polybench.schemas import Task, Language, Difficulty

class TaskRegistry:
    def __init__(self, tasks: Iterable[Task]) -> None:
        self._tasks = list(tasks)
        
    def filter(
        self,
        lang: Optional[str] = None,
        difficulty: Optional[Difficulty] = None,
        tags: Optional[list[str]] = None,
    ) -> list[Task]:
        """Filters tasks by language, difficulty, and required tags."""
        result = self._tasks
        if lang is not None:
            result = [t for t in result if t.language == lang]
        if difficulty is not None:
            result = [t for t in result if t.difficulty == difficulty]
        if tags:
            result = [t for t in result if all(tag in t.tags for tag in tags)]
        return result
