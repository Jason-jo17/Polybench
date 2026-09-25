from pydantic import BaseModel, Field, field_validator
from enum import StrEnum
from typing import Optional


class Language(StrEnum):
    python = "python"
    javascript = "javascript"
    go = "go"
    rust = "rust"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Task(BaseModel):
    id: str  # "python/lru_cache" — must match path
    language: str  # str to support any custom language
    difficulty: Difficulty
    title: str
    prompt: str  # the problem statement shown to the model
    signature: str  # required function/class signature
    test_code: str  # HIDDEN test suite (never shown to model)
    # A known-correct solution, also never shown to the model. `polybench tasks
    # verify` checks that it passes the tests and the bare signature doesn't.
    reference_solution: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=10, ge=1, le=60)

    # Optional execution spec overrides to support any tech stack dynamically
    image: Optional[str] = None
    code_file: Optional[str] = None
    test_file: Optional[str] = None
    test_cmd: Optional[list[str]] = None

    @field_validator("test_code")
    @classmethod
    def non_empty_tests(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("test_code must not be empty")
        return v


class TestCase(BaseModel):
    name: str
    code: str


class GenerationResult(BaseModel):
    raw_output: str
    runtime_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class ScoreReport(BaseModel):
    run_id: str
    model: str
    pass_at_k: float
    task_results: list[dict[str, str | float]]
