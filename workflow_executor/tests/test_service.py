from __future__ import annotations

import asyncio
from types import SimpleNamespace
from pathlib import Path

from workflow_executor.config import Settings
from workflow_executor.models import ExecuteStageRequest, NodeProfile, StageExecutionSpec, StageMetadata
from workflow_executor.service import WorkflowExecutorService


class DummyAsyncResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    def __init__(self, responses: list[DummyAsyncResponse], sent: list[dict], **kwargs) -> None:
        self._responses = responses
        self._sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self._sent.append({"url": url, "json": json})
        return self._responses.pop(0)


class FakeBatchApi:
    def __init__(self) -> None:
        self.created_jobs = []
        self.read_count = 0

    def create_namespaced_job(self, namespace, body):
        self.created_jobs.append({"namespace": namespace, "body": body})

    def read_namespaced_job_status(self, name, namespace):
        self.read_count += 1
        return SimpleNamespace(status=SimpleNamespace(succeeded=1, failed=0))


def _sample_request() -> ExecuteStageRequest:
    return ExecuteStageRequest(
        workflow_id="wf-1",
        workflow_type="vision_pipeline",
        stage=StageExecutionSpec(
            stage_id="inference",
            stage_metadata=StageMetadata(
                stage_type="inference",
                requires_accelerator=True,
                compute_intensity="high",
                memory_intensity="medium",
                latency_sensitivity="medium",
                input_size_kb=1024,
                output_size_kb=256,
            ),
            image="busybox:1.36",
            command=["sh", "-lc"],
            args=["echo run && sleep 1"],
            exec_time_ms=1000,
        ),
        node_profiles=[
            NodeProfile(
                hostname="etri-ser0001-CG0MSB",
                node_type="cloud_server",
                arch="x86_64",
                compute_class="high",
                memory_class="high",
                accelerator_type="gpu_server",
            )
        ],
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        state_db_path=tmp_path / "workflow_state.db",
    )


def test_execute_stage_creates_job_and_reports_events(monkeypatch, tmp_path: Path):
    sent = []
    responses = [
        DummyAsyncResponse(
            {
                "decision": {
                    "workflow_id": "wf-1",
                    "stage_id": "inference",
                    "target_node": "etri-ser0001-CG0MSB",
                    "decision_reason": "selected server",
                    "action_type": "migrate",
                    "score_breakdown": {},
                }
            }
        ),
        DummyAsyncResponse({"ok": True}),
        DummyAsyncResponse({"ok": True}),
    ]
    batch_api = FakeBatchApi()
    monkeypatch.setattr(
        "workflow_executor.service.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(responses, sent, **kwargs),
    )
    service = WorkflowExecutorService(_settings(tmp_path), batch_api=batch_api)

    result = asyncio.run(service.execute_stage(_sample_request()))

    assert result.status == "completed"
    assert result.target_node == "etri-ser0001-CG0MSB"
    assert batch_api.created_jobs[0]["body"].spec.template.spec.node_selector == {
        "kubernetes.io/hostname": "etri-ser0001-cg0msb"
    }
    assert sent[0]["json"]["stage_id"] == "inference"
    assert sent[1]["json"]["event_type"] == "stage_start"
    assert sent[2]["json"]["event_type"] == "stage_end"
    workflow = asyncio.run(service.get_workflow_state("wf-1"))
    assert workflow.current_stage_id == "inference"
    assert workflow.stages[0].job_name is not None
    assert workflow.transitions[-1].status == "stage_completed"


def test_execute_stage_reports_migration(monkeypatch, tmp_path: Path):
    sent = []
    responses = [
        DummyAsyncResponse(
            {
                "decision": {
                    "workflow_id": "wf-1",
                    "stage_id": "inference",
                    "target_node": "etri-ser0001-CG0MSB",
                    "decision_reason": "selected server",
                    "action_type": "offload_to_cloud",
                    "score_breakdown": {},
                }
            }
        ),
        DummyAsyncResponse({"ok": True}),
        DummyAsyncResponse({"ok": True}),
        DummyAsyncResponse({"ok": True}),
    ]
    batch_api = FakeBatchApi()
    monkeypatch.setattr(
        "workflow_executor.service.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(responses, sent, **kwargs),
    )
    service = WorkflowExecutorService(_settings(tmp_path), batch_api=batch_api)
    request = _sample_request()
    request.current_placement = "etri-dev0001-jetorn"

    asyncio.run(service.execute_stage(request))

    assert sent[1]["json"]["event_type"] == "migration_event"
    assert sent[1]["json"]["from_node"] == "etri-dev0001-jetorn"
    workflow = asyncio.run(service.get_workflow_state("wf-1"))
    assert any(item.status == "migration_event" for item in workflow.transitions)
