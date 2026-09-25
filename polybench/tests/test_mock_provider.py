from polybench.config import PROJECT_ROOT
from polybench.extract import extract_code
from polybench.providers.mock_provider import MockProvider
from polybench.tasks.loader import load_tasks

TASKS = {t.id: t for t in load_tasks(PROJECT_ROOT / "tasks")}


def _prompt(task_id: str) -> str:
    # Same shape as the prompt the engine builds.
    t = TASKS[task_id]
    return f"Language: {t.language}\nRequired signature:\n{t.signature}\n\nTask:\n{t.prompt}"


def test_perfect_answers_with_the_reference_solution_in_every_language():
    provider = MockProvider(model="perfect")
    for task_id in ("python/two_sum", "javascript/memoize", "go/stack", "rust/sum"):
        task = TASKS[task_id]
        raw = provider.generate(_prompt(task_id)).raw_output
        assert (
            extract_code(raw, task.language).strip() == task.reference_solution.strip()
        )


def test_broken_answers_with_the_bare_signature():
    task = TASKS["python/two_sum"]
    raw = MockProvider(model="broken").generate(_prompt(task.id)).raw_output
    assert extract_code(raw, "python").strip() == task.signature.strip()


def test_demo_mix_is_deterministic_and_roughly_matches_its_rate():
    def outcomes(model):
        provider = MockProvider(model=model)
        ref = TASKS["python/two_sum"].reference_solution.strip()
        return [
            ref in provider.generate(_prompt("python/two_sum")).raw_output
            for _ in range(200)
        ]

    first = outcomes("demo-40")
    assert first == outcomes("demo-40")
    assert 50 <= sum(first) <= 110  # ~40% of 200
    assert 110 <= sum(outcomes("demo")) <= 170  # ~70% of 200


def test_unknown_prompt_gets_the_fallback_answer():
    provider = MockProvider(model="test")
    assert "return 42" in provider.generate("Write something unrelated").raw_output
    provider.should_pass = False
    assert "mock fail" in provider.generate("Write something unrelated").raw_output
