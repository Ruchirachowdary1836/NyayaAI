from __future__ import annotations

import uuid

from backend.app.db.database import DatabaseConfig, as_database
from backend.app.schemas.retrieval import FeedbackRequest, FeedbackResponse
from fastapi import APIRouter, Request

router = APIRouter(prefix="/feedback", tags=["feedback"])


def initialize_feedback_store(store_config: DatabaseConfig) -> None:
    as_database(store_config).initialize()


@router.post("", response_model=FeedbackResponse, status_code=201)
def submit_feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    feedback_id = str(uuid.uuid4())
    database = as_database(request.app.state.feedback_db)
    database.insert_feedback(
        feedback_id,
        payload.query,
        payload.rating,
        payload.correctness,
        payload.comment,
    )
    return FeedbackResponse(accepted=True, feedback_id=feedback_id)
