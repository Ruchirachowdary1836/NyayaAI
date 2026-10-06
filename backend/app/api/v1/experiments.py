from fastapi import APIRouter

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("")
def experiments_placeholder() -> dict[str, str]:
    return {"status": "experiments dashboard pending"}
