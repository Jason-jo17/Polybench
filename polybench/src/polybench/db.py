from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

engine: Engine | None = None


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable FK enforcement and WAL mode on every new SQLite connection."""
    if engine and engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
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

    # Register the table models on SQLModel.metadata; create_all only creates
    # tables for models that have been imported.
    import polybench.models  # noqa: F401

    if engine is not None:
        engine.dispose()
    engine = create_engine(db_url)
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(db: Engine) -> None:
    """Add nullable columns introduced after a database was created.

    create_all() makes missing tables but never alters existing ones, so a new
    optional model field would otherwise break older databases. Only nullable
    columns can be added this way; anything else needs a real migration.
    """
    inspector = inspect(db)
    with db.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    raise RuntimeError(
                        f"Column {table.name}.{column.name} is missing from the database "
                        "and isn't nullable, so it can't be added automatically."
                    )
                col_type = column.type.compile(dialect=db.dialect)
                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                    )
                )


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
