from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

engine: Engine | None = None


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
    """Enable FK enforcement and WAL mode on every new SQLite connection."""
    if engine and engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def init_db(db_url: str | None = None) -> None:
    global engine
    # if no db_url is provided, fall back to settings
    if not db_url:
        from polybench.config import settings

        db_url = settings.polybench_db

    if not db_url.startswith(
        ("sqlite:", "postgresql:", "mysql:", "postgresql+psycopg2:")
    ):
        # if they passed a bare path, assume sqlite
        db_url = f"sqlite:///{db_url}"

    engine = create_engine(db_url)
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db first.")
    with Session(engine) as session:
        yield session


def get_api_session() -> Generator[Session, None, None]:
    if engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db first.")
    with Session(engine) as session:
        yield session
