from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}")
def document_placeholder(document_id: str) -> dict[str, str]:
    return {"document_id": document_id, "status": "document viewer pending"}
