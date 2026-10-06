from fastapi import APIRouter

router = APIRouter(prefix="/qa", tags=["qa"])


@router.get("")
def qa_placeholder() -> dict[str, str]:
    return {"status": "qa pipeline pending"}
