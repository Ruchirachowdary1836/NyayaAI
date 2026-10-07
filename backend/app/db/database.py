from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("username", String(80), primary_key=True),
    Column("password_hash", LargeBinary, nullable=False),
    Column("password_salt", LargeBinary, nullable=False),
    Column("role", String(8), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
)
feedback = Table(
    "feedback",
    metadata,
    Column("feedback_id", String(36), primary_key=True),
    Column("query", Text, nullable=False),
    Column("rating", String(4), nullable=False),
    Column("correctness", Integer),
    Column("comment", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("rating IN ('up', 'down')", name="ck_feedback_rating"),
)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class Database:
    def __init__(self, url: str) -> None:
        url = _normalize_database_url(url)
        if url.startswith("sqlite:///"):
            database_file = Path(url.removeprefix("sqlite:///"))
            database_file.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {},
        )

    @classmethod
    def from_path(cls, path: Path) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            URL.create("sqlite", database=str(path.resolve())).render_as_string(hide_password=False)
        )

    def initialize(self) -> None:
        metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def create_user(
        self, username: str, password_hash: bytes, password_salt: bytes, role: str
    ) -> bool:
        try:
            with self.engine.begin() as connection:
                exists = connection.execute(
                    select(users.c.username).where(users.c.username == username)
                ).first()
                if exists:
                    return False
                connection.execute(
                    insert(users).values(
                        username=username,
                        password_hash=password_hash,
                        password_salt=password_salt,
                        role=role,
                    )
                )
        except IntegrityError:
            return False
        return True

    def get_user_credentials(self, username: str):
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    users.c.password_hash,
                    users.c.password_salt,
                    users.c.role,
                ).where(users.c.username == username)
            ).first()
        return row

    def get_user_role(self, username: str) -> str | None:
        with self.engine.connect() as connection:
            role = connection.execute(
                select(users.c.role).where(users.c.username == username)
            ).scalar_one_or_none()
        return role

    def update_user_credentials(
        self,
        current_username: str,
        new_username: str,
        password_hash: bytes | None = None,
        password_salt: bytes | None = None,
    ) -> bool:
        values: dict[str, object] = {"username": new_username}
        if password_hash is not None and password_salt is not None:
            values.update(password_hash=password_hash, password_salt=password_salt)
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(users).where(users.c.username == current_username).values(**values)
                )
        except IntegrityError:
            return False
        return result.rowcount == 1

    def get_user_profile(self, username: str) -> tuple[str, str] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(users.c.username, users.c.role).where(users.c.username == username)
            ).first()
        return (str(row.username), str(row.role)) if row else None

    def list_users(self) -> list[tuple[str, str, str]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(users.c.username, users.c.role, users.c.created_at).order_by(
                    users.c.created_at.desc()
                )
            ).all()
        return [(row.username, row.role, row.created_at.isoformat()) for row in rows]

    def count_users(self) -> int:
        with self.engine.connect() as connection:
            return int(connection.execute(select(func.count()).select_from(users)).scalar_one())

    def insert_feedback(
        self,
        feedback_id: str,
        query: str,
        rating: str,
        correctness: int | None,
        comment: str | None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(feedback).values(
                    feedback_id=feedback_id,
                    query=query,
                    rating=rating,
                    correctness=correctness,
                    comment=comment,
                )
            )


DatabaseConfig = str | Path | Database


def as_database(value: DatabaseConfig) -> Database:
    if isinstance(value, Database):
        return value
    return Database.from_path(value) if isinstance(value, Path) else Database(value)
