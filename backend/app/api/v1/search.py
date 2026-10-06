from fastapi import APIRouter

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
