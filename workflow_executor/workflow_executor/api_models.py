from __future__ import annotations

from pydantic import BaseModel

from .models import (
    ExecuteStageRequest,
    ExecuteWorkflowRequest,
    StageExecutionResult,
    WorkflowExecutionResult,
)


class ExecuteStageResponse(BaseModel):
    result: StageExecutionResult


class ExecuteWorkflowResponse(BaseModel):
    result: WorkflowExecutionResult


__all__ = [
    "ExecuteStageRequest",
    "ExecuteStageResponse",
    "ExecuteWorkflowRequest",
    "ExecuteWorkflowResponse",
]
