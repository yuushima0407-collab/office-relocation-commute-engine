from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from cest.models.request import EvaluateRequest
from cest.engine.pipeline import evaluate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluate"])


@router.post("/evaluate")
def post_evaluate(body: EvaluateRequest):
    try:
        inputs = body.inputs.model_dump()
        result = evaluate(inputs)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error in /evaluate")
        raise HTTPException(status_code=500, detail="Internal server error")
