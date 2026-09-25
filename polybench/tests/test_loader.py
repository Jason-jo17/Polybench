import json
from polybench.tasks.loader import load_tasks

def test_load_tasks(tmp_path):
    t_dir = tmp_path / "tasks"
    t_dir.mkdir()
    f = t_dir / "t1.json"
    f.write_text(json.dumps({
        "id": "test/task",
        "language": "python",
        "difficulty": "easy",
        "title": "T",
        "prompt": "P",
        "signature": "S",
        "test_code": "code"
    }))
    tasks = list(load_tasks(t_dir))
    assert len(tasks) == 1
    assert tasks[0].id == "test/task"

def test_task_registry():
    from polybench.tasks.registry import TaskRegistry
    from polybench.schemas import Task, Difficulty
    
    t1 = Task(id="p1", language="python", difficulty=Difficulty.easy, title="T1", prompt="P", signature="S", test_code="pass", tags=["math"])
    t2 = Task(id="p2", language="javascript", difficulty=Difficulty.medium, title="T2", prompt="P", signature="S", test_code="pass", tags=["string"])
    t3 = Task(id="p3", language="python", difficulty=Difficulty.hard, title="T3", prompt="P", signature="S", test_code="pass", tags=["math", "graph"])
    
    registry = TaskRegistry([t1, t2, t3])
    
    # test filter lang
    assert len(registry.filter(lang="python")) == 2
    
    # test filter difficulty
    assert len(registry.filter(difficulty=Difficulty.medium)) == 1
    
    # test filter tags
    assert len(registry.filter(tags=["math"])) == 2
    assert len(registry.filter(tags=["math", "graph"])) == 1
    
    # test multiple filters
    res = registry.filter(lang="python", difficulty=Difficulty.hard, tags=["graph"])
    assert len(res) == 1
    assert res[0].id == "p3"

