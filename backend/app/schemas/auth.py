from typing import Literal

from pydantic import BaseModel, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


class Credentials(BaseModel):
    """Login credentials. Username format is enforced at registration, not here."""

    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in: int


class ProfileUpdate(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    username: str = Field(min_length=3, max_length=80, pattern=USERNAME_PATTERN)
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


class UserProfile(BaseModel):
    username: str
    role: Literal["user", "admin"]
    is_active: bool
    created_at: str | None
    last_login_at: str | None


class UserResponse(UserProfile):
    pass


class UserList(BaseModel):
    users: list[UserResponse]
    total: int
    limit: int
    offset: int


class UserAccessUpdate(BaseModel):
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


class AdminOverview(BaseModel):
    corpus_documents: int
    corpus_chunks: int
    experiment_runs: int
    benchmark_runs: int
    users: int
    active_users: int
    users_active_last_7_days: int
    uploaded_documents: dict[str, int]
    uploaded_bytes: int
    feedback: dict[str, int]
    usage_last_24h: list[dict[str, object]]
    usage_last_7d: list[dict[str, object]]
    retrievers: dict[str, dict[str, object]]
    ingestion: dict[str, object]
    system: dict[str, object]
