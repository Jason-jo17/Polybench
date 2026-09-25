import json
from pathlib import Path
from collections.abc import Generator

from polybench.schemas import Task

def load_tasks(tasks_dir: str | Path) -> Generator[Task, None, None]:
    """Loads and validates all task JSON files from a directory recursively."""
    path = Path(tasks_dir)
    if not path.exists() or not path.is_dir():
        return
        
    for json_file in path.rglob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            yield Task.model_validate(data)
