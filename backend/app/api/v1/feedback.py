from fastapi import APIRouter

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("")
def feedback_placeholder() -> dict[str, str]:
    return {"status": "feedback endpoint pending"}
