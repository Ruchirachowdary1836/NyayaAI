from __future__ import annotations

import uuid

from fastapi import APIRouter

from backend.app.api.deps import DB, CurrentUser
from backend.app.schemas.retrieval import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=201)
def submit_feedback(payload: FeedbackRequest, user: CurrentUser, database: DB) -> FeedbackResponse:
    feedback_id = str(uuid.uuid4())
    database.insert_feedback(
        feedback_id,
        payload.query,
        payload.rating,
        payload.correctness,
        payload.comment,
        username=user["username"],
    )
    return FeedbackResponse(accepted=True, feedback_id=feedback_id)
