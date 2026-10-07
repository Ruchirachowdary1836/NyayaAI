from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ProfileUpdate(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


class UserResponse(BaseModel):
    username: str
    role: str
    created_at: str


class AdminOverview(BaseModel):
    corpus_documents: int
    corpus_chunks: int
    experiment_runs: int
    users: int
