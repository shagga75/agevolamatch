from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DB_PATH = Path("data/agevolamatch.db")


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)


def get_session(engine) -> Session:
    return Session(engine)
