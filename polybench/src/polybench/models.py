from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid


def _id() -> str:
    return uuid.uuid4().hex


class BenchmarkRun(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model: str
    provider: str
    language_filter: str | None = None
    samples_per_task: int
    k: int
    temperature: float
    total_tasks: int
    pass_at_k: float
    status: str = Field(default="PENDING")
    git_sha: str | None = None


class TaskResult(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = Field(foreign_key="benchmarkrun.id", index=True)
    task_id: str = Field(index=True)
    language: str
    difficulty: str
    samples_generated: int
    samples_passed: int
    task_pass_at_k: float
    sandbox_image: str | None = None
    sandbox_test_cmd: str | None = None


class Sample(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_result_id: str = Field(foreign_key="taskresult.id", index=True)
    sample_index: int
    raw_output: str
    extracted_code: str | None = None
    passed: bool
    failure_kind: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    runtime_ms: int = 0
    timed_out: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
