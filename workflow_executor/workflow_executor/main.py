from __future__ import annotations

from fastapi import FastAPI

from .api_models import (
    ExecuteStageRequest,
    ExecuteStageResponse,
    ExecuteWorkflowRequest,
    ExecuteWorkflowResponse,
)
from .config import Settings
from .service import WorkflowExecutorService

settings = Settings()
service = WorkflowExecutorService(settings)

app = FastAPI(title="workflow-executor", version="0.1.0")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/execute/stage", response_model=ExecuteStageResponse)
async def execute_stage(request: ExecuteStageRequest) -> ExecuteStageResponse:
    result = await service.execute_stage(request)
    return ExecuteStageResponse(result=result)


@app.post("/execute/workflow", response_model=ExecuteWorkflowResponse)
async def execute_workflow(request: ExecuteWorkflowRequest) -> ExecuteWorkflowResponse:
    result = await service.execute_workflow(request)
    return ExecuteWorkflowResponse(result=result)
