from fastapi import APIRouter

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("")
def compare_placeholder() -> dict[str, list[str]]:
    return {"retrievers": ["bm25", "dense", "hybrid"]}
