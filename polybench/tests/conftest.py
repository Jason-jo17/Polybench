import pytest
from sqlmodel import SQLModel
from polybench.db import init_db, engine
from polybench.providers.mock_provider import MockProvider
from polybench.schemas import Task, Language, Difficulty

@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(f"sqlite:///{db_file}")
    yield db_file
    if engine:
        SQLModel.metadata.drop_all(engine)

@pytest.fixture
def mock_provider():
    return MockProvider(model="test")

@pytest.fixture
def sample_task():
    return Task(
        id="test/task",
        language=Language.python,
        difficulty=Difficulty.easy,
        title="Test Task",
        prompt="Do something",
        signature="def test(): pass",
        test_code="def check(): pass",
        tags=["test"]
    )
