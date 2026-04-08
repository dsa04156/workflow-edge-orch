from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone

import httpx
from kubernetes import client

from .config import Settings
from .kube import build_batch_api
from .models import (
    ExecuteStageRequest,
    ExecuteWorkflowRequest,
    PlacementDecision,
    StageExecutionResult,
    StageExecutionSpec,
    WorkflowEvent,
    WorkflowExecutionResult,
)


def _sanitize_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return name[:50] or "stage"


class WorkflowExecutorService:
    def __init__(self, settings: Settings, batch_api: client.BatchV1Api | None = None) -> None:
        self.settings = settings
        self.batch_api = batch_api or build_batch_api()
        self.current_placement: dict[tuple[str, str], str] = {}

    async def execute_stage(self, request: ExecuteStageRequest) -> StageExecutionResult:
        decision = await self._decide_stage(
            workflow_id=request.workflow_id,
            workflow_type=request.workflow_type,
            stage=request.stage,
            node_profiles=[profile.model_dump() for profile in request.node_profiles],
            current_placement=request.current_placement,
        )
        if not decision.target_node or decision.action_type == "reject":
            await self._send_event(
                WorkflowEvent(
                    event_type="failure_event",
                    workflow_id=request.workflow_id,
                    workflow_type=request.workflow_type,
                    stage_id=request.stage.stage_id,
                    stage_type=request.stage.stage_metadata.stage_type,
                    assigned_node=request.current_placement or "unassigned",
                    reason=decision.decision_reason,
                    status="failed",
                )
            )
            raise RuntimeError(f"Stage rejected: {decision.decision_reason}")

        previous_node = request.current_placement
        if previous_node and previous_node != decision.target_node:
            await self._send_event(
                WorkflowEvent(
                    event_type="migration_event",
                    workflow_id=request.workflow_id,
                    workflow_type=request.workflow_type,
                    stage_id=request.stage.stage_id,
                    stage_type=request.stage.stage_metadata.stage_type,
                    assigned_node=decision.target_node,
                    from_node=previous_node,
                    to_node=decision.target_node,
                    transfer_time_ms=request.stage.transfer_time_ms,
                    reason=decision.decision_reason,
                    status="migrating",
                )
            )

        job_name = await asyncio.to_thread(
            self._create_job,
            workflow_id=request.workflow_id,
            workflow_type=request.workflow_type,
            stage=request.stage,
            target_node=decision.target_node,
        )

        await self._send_event(
            WorkflowEvent(
                event_type="stage_start",
                workflow_id=request.workflow_id,
                workflow_type=request.workflow_type,
                stage_id=request.stage.stage_id,
                stage_type=request.stage.stage_metadata.stage_type,
                assigned_node=decision.target_node,
                queue_wait_ms=request.stage.queue_wait_ms,
                status="running",
            )
        )

        status = await asyncio.to_thread(
            self._wait_for_job,
            job_name,
            request.stage.timeout_seconds or self.settings.job_timeout_seconds,
        )

        if status != "completed":
            await self._send_event(
                WorkflowEvent(
                    event_type="failure_event",
                    workflow_id=request.workflow_id,
                    workflow_type=request.workflow_type,
                    stage_id=request.stage.stage_id,
                    stage_type=request.stage.stage_metadata.stage_type,
                    assigned_node=decision.target_node,
                    reason=f"job {job_name} failed",
                    status="failed",
                )
            )
            raise RuntimeError(f"Job {job_name} failed")

        await self._send_event(
            WorkflowEvent(
                event_type="stage_end",
                workflow_id=request.workflow_id,
                workflow_type=request.workflow_type,
                stage_id=request.stage.stage_id,
                stage_type=request.stage.stage_metadata.stage_type,
                assigned_node=decision.target_node,
                exec_time_ms=request.stage.exec_time_ms,
                status="completed",
            )
        )

        self.current_placement[(request.workflow_id, request.stage.stage_id)] = decision.target_node
        return StageExecutionResult(
            workflow_id=request.workflow_id,
            workflow_type=request.workflow_type,
            stage_id=request.stage.stage_id,
            target_node=decision.target_node,
            action_type=decision.action_type,
            decision_reason=decision.decision_reason,
            job_name=job_name,
            status="completed",
        )

    async def execute_workflow(self, request: ExecuteWorkflowRequest) -> WorkflowExecutionResult:
        results: list[StageExecutionResult] = []
        placement = dict(request.current_placement)

        for stage in request.stages:
            result = await self.execute_stage(
                ExecuteStageRequest(
                    workflow_id=request.workflow_id,
                    workflow_type=request.workflow_type,
                    stage=stage,
                    node_profiles=request.node_profiles,
                    current_placement=placement.get(stage.stage_id),
                )
            )
            placement[stage.stage_id] = result.target_node
            results.append(result)

        last_stage = request.stages[-1]
        last_target = results[-1].target_node
        await self._send_event(
            WorkflowEvent(
                event_type="workflow_end",
                workflow_id=request.workflow_id,
                workflow_type=request.workflow_type,
                stage_id=last_stage.stage_id,
                stage_type=last_stage.stage_metadata.stage_type,
                assigned_node=last_target,
                status="completed",
            )
        )
        return WorkflowExecutionResult(
            workflow_id=request.workflow_id,
            workflow_type=request.workflow_type,
            stages=results,
        )

    async def _decide_stage(
        self,
        *,
        workflow_id: str,
        workflow_type: str,
        stage: StageExecutionSpec,
        node_profiles: list[dict],
        current_placement: str | None,
    ) -> PlacementDecision:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.post(
                f"{self.settings.placement_engine_url.rstrip('/')}/placement/decide",
                json={
                    "workflow_id": workflow_id,
                    "workflow_type": workflow_type,
                    "stage_id": stage.stage_id,
                    "stage_metadata": stage.stage_metadata.model_dump(),
                    "node_profiles": node_profiles,
                    "current_placement": current_placement,
                },
            )
            response.raise_for_status()
        return PlacementDecision(**response.json()["decision"])

    async def _send_event(self, event: WorkflowEvent) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.post(
                self.settings.state_aggregator_event_url,
                json=event.model_dump(mode="json"),
            )
            response.raise_for_status()

    def _create_job(
        self,
        *,
        workflow_id: str,
        workflow_type: str,
        stage: StageExecutionSpec,
        target_node: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        job_name = f"{_sanitize_name(workflow_id)}-{_sanitize_name(stage.stage_id)}-{timestamp}"
        env = [
            client.V1EnvVar(name=key, value=value)
            for key, value in sorted(stage.env.items())
        ]
        env.extend(
            [
                client.V1EnvVar(name="WORKFLOW_ID", value=workflow_id),
                client.V1EnvVar(name="WORKFLOW_TYPE", value=workflow_type),
                client.V1EnvVar(name="STAGE_ID", value=stage.stage_id),
                client.V1EnvVar(name="STAGE_TYPE", value=stage.stage_metadata.stage_type),
                client.V1EnvVar(name="TARGET_NODE", value=target_node),
            ]
        )
        container = client.V1Container(
            name="stage",
            image=stage.image,
            command=stage.command or None,
            args=stage.args or None,
            env=env or None,
        )
        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
            node_selector={"kubernetes.io/hostname": target_node.lower()},
        )
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": "workflow-executor-stage",
                    "workflow_id": _sanitize_name(workflow_id),
                    "stage_id": _sanitize_name(stage.stage_id),
                }
            ),
            spec=pod_spec,
        )
        body = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={
                    "app": "workflow-executor-stage",
                    "workflow_id": _sanitize_name(workflow_id),
                    "workflow_type": _sanitize_name(workflow_type),
                    "stage_id": _sanitize_name(stage.stage_id),
                    "target_node": target_node.lower(),
                },
            ),
            spec=client.V1JobSpec(
                template=template,
                backoff_limit=0,
                ttl_seconds_after_finished=300,
            ),
        )
        self.batch_api.create_namespaced_job(namespace=self.settings.namespace, body=body)
        return job_name

    def _wait_for_job(self, job_name: str, timeout_seconds: int) -> str:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = self.batch_api.read_namespaced_job_status(
                name=job_name,
                namespace=self.settings.namespace,
            )
            status = job.status
            if status.succeeded and status.succeeded >= 1:
                return "completed"
            if status.failed and status.failed >= 1:
                return "failed"
            time.sleep(self.settings.poll_interval_seconds)
        return "failed"
