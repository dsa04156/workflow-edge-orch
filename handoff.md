# Handoff

## Current status

This repository now has five working pieces connected end-to-end:

1. `state_aggregator`
2. `workflow_reporter`
3. `placement_engine`
4. `workflow_executor` (thin executor prototype)
5. `vision_stage_runner` (multi-arch synthetic stage payload)

The current system is no longer only making placement decisions.
It now supports:

- Prometheus metric ingestion into `state_aggregator`
- normalized node/workflow state exposure
- Prometheus scrape of `state_aggregator` `/metrics`
- Grafana dashboard JSON for the aggregator metrics
- workflow event reporting
- heuristic placement decisions
- actual Kubernetes `Job` creation from placement decisions through `workflow_executor`
- actual stage payload execution across x86 and ARM nodes

## What was implemented

### 1. `state_aggregator`

Location:
- [state-aggregator/app/main.py](/home/etri/jinuk/edge-orch/state-aggregator/app/main.py)
- [state-aggregator/app/service.py](/home/etri/jinuk/edge-orch/state-aggregator/app/service.py)
- [state-aggregator/app/prometheus.py](/home/etri/jinuk/edge-orch/state-aggregator/app/prometheus.py)
- [state-aggregator/app/metrics.py](/home/etri/jinuk/edge-orch/state-aggregator/app/metrics.py)

Implemented:
- periodic Prometheus polling
- node metric normalization
- workflow event ingestion
- summary state generation
- `/metrics` endpoint in Prometheus exposition format

Current deployment state:
- deployed in `default` namespace
- ServiceMonitor applied
- Prometheus target is active and healthy

Confirmed:
- `/metrics` returns `edge_orch_*` metrics
- Prometheus active targets include `state-aggregator`

### 2. Grafana dashboard

Location:
- [state-aggregator/grafana/state-aggregator-dashboard.json](/home/etri/jinuk/edge-orch/state-aggregator/grafana/state-aggregator-dashboard.json)

Includes panels for:
- tracked nodes
- hotspot nodes
- high SLA risk workflows
- recent migrations
- CPU/memory/network
- normalized node state
- workflow control state

### 3. `workflow_reporter`

Location:
- [workflow_reporter/workflow_reporter/client.py](/home/etri/jinuk/edge-orch/workflow_reporter/workflow_reporter/client.py)
- [workflow_reporter/workflow_reporter/helpers.py](/home/etri/jinuk/edge-orch/workflow_reporter/workflow_reporter/helpers.py)
- [workflow_reporter/workflow_reporter/demo_workflow.py](/home/etri/jinuk/edge-orch/workflow_reporter/workflow_reporter/demo_workflow.py)

Implemented:
- `stage_start`
- `stage_end`
- `migration_event`
- `failure_event`
- `workflow_end`
- fallback JSONL logging on failure

Also added:
- 5-stage vision pipeline demo runner

Important distinction:
- `workflow_reporter.demo_workflow` is still a demo runner path
- it validates decision + event flow
- it does not directly create per-stage Kubernetes Jobs

### 4. `placement_engine`

Location:
- [placement_engine/placement_engine/engine.py](/home/etri/jinuk/edge-orch/placement_engine/placement_engine/engine.py)
- [placement_engine/placement_engine/main.py](/home/etri/jinuk/edge-orch/placement_engine/placement_engine/main.py)

Implemented:
- heuristic stage placement logic
- `/placement/decide`
- `/placement/replan`

Observed behavior in current cluster:
- `capture`, `preprocess`, `result_delivery` prefer Raspberry Pi
- `inference`, `postprocess` prefer server for the current demo inputs

### 5. `workflow_executor`

Location:
- [workflow_executor/workflow_executor/main.py](/home/etri/jinuk/edge-orch/workflow_executor/workflow_executor/main.py)
- [workflow_executor/workflow_executor/service.py](/home/etri/jinuk/edge-orch/workflow_executor/workflow_executor/service.py)
- [workflow_executor/workflow_executor/models.py](/home/etri/jinuk/edge-orch/workflow_executor/workflow_executor/models.py)

Implemented:
- `POST /execute/stage`
- `POST /execute/workflow`
- placement lookup through `placement_engine`
- actual Kubernetes `Job` creation per stage
- wait for stage Job completion
- event emission to `state_aggregator`
- in-memory current placement tracking inside executor process

Deployment files:
- [workflow_executor/k8s/deployment.yaml](/home/etri/jinuk/edge-orch/workflow_executor/k8s/deployment.yaml)
- [workflow_executor/k8s/rbac.yaml](/home/etri/jinuk/edge-orch/workflow_executor/k8s/rbac.yaml)
- [workflow_executor/k8s/demo-request.json](/home/etri/jinuk/edge-orch/workflow_executor/k8s/demo-request.json)

### 6. `vision_stage_runner`

Location:
- [vision_stage_runner/vision_stage_runner/main.py](/home/etri/jinuk/edge-orch/vision_stage_runner/vision_stage_runner/main.py)

Implemented:
- one reusable stage image for:
  - `capture`
  - `preprocess`
  - `inference`
  - `postprocess`
  - `result_delivery`
- deterministic synthetic stage logic keyed by `workflow_id`
- stage context via env:
  - `WORKFLOW_ID`
  - `WORKFLOW_TYPE`
  - `STAGE_ID`
  - `STAGE_TYPE`
  - `TARGET_NODE`
- multi-arch image build for `linux/amd64` and `linux/arm64`

Important:
- this is not yet a real AI inference stack
- it replaced `busybox + sleep` with executable synthetic stage logic
- it is the image used by the executor demo request now

## What was actually verified

### Verified locally via tests

`state_aggregator`
- tests passed from its virtualenv

`workflow_reporter`
- tests passed using the existing Python environment with `PYTHONPATH=.`

`workflow_executor`
- tests passed in its own virtualenv

### Verified on the cluster

`state_aggregator`
- rollout succeeded
- `/metrics` reachable
- Prometheus scraping confirmed

`workflow_reporter` demo job
- vision pipeline demo job completed
- workflow state appeared in aggregator

`workflow_executor`
- deployed and healthy
- actual workflow request executed successfully
- actual stage Jobs created and completed
- workflow state updated in aggregator

`vision_stage_runner`
- tests passed in its own virtualenv
- multi-arch image build succeeded with `docker buildx`
- ARM-targeted stages successfully pulled and ran after the multi-arch rebuild

## Latest successful executor run

Workflow ID:
- `wf-exec-demo-001`

Request file:
- [workflow_executor/k8s/demo-request.json](/home/etri/jinuk/edge-orch/workflow_executor/k8s/demo-request.json)

Successful 5-stage execution result:
- `capture` -> `etri-dev0002-raspi5`
- `preprocess` -> `etri-dev0002-raspi5`
- `inference` -> `etri-ser0001-CG0MSB`
- `postprocess` -> `etri-ser0001-CG0MSB`
- `result_delivery` -> `etri-dev0002-raspi5`

Observed stage Job names from the latest successful multi-arch run:
- `wf-exec-demo-001-capture-050353`
- `wf-exec-demo-001-preprocess-050405`
- `wf-exec-demo-001-inference-050409`
- `wf-exec-demo-001-postprocess-050413`
- `wf-exec-demo-001-result-delivery-050418`

Aggregator confirmation:
- `wf-exec-demo-001` appears in `/state/workflows`
- latest event is `workflow_end`

Cross-architecture confirmation:
- `capture`, `preprocess`, `result_delivery` completed on Raspberry Pi using `vision-stage-runner`
- `inference`, `postprocess` completed on the server using `vision-stage-runner`

## Images and deployments

Current deployed images use pushed digests in manifest files for the components that were updated during this work.

Notable manifests:
- [state-aggregator/k8s/deployment.yaml](/home/etri/jinuk/edge-orch/state-aggregator/k8s/deployment.yaml)
- [state-aggregator/k8s/service-monitor.yaml](/home/etri/jinuk/edge-orch/state-aggregator/k8s/service-monitor.yaml)
- [workflow_reporter/k8s/vision-pipeline-job.yaml](/home/etri/jinuk/edge-orch/workflow_reporter/k8s/vision-pipeline-job.yaml)
- [workflow_executor/k8s/deployment.yaml](/home/etri/jinuk/edge-orch/workflow_executor/k8s/deployment.yaml)

Latest multi-arch image note:
- `vision-stage-runner:latest` was rebuilt with `docker buildx`
- pushed manifest list digest:
  - `sha256:42e2208f53502ec8e18f4aa8fc282a5124a50c385198e28c58e0f688d5a56c3f`

## Known limitations

1. `workflow_executor` is a thin synchronous prototype.
It waits for each stage `Job` to complete before moving to the next stage.

2. Migration is not yet a real runtime move of an already running stage.
Current behavior is:
- placement is recalculated per stage
- executor can emit `migration_event`
- but there is no live stage takeover or checkpoint-based migration

3. Current stage containers are still synthetic workload containers.
They no longer use `busybox + sleep`, but they do not yet run a real AI model pipeline.

4. Current placement tracking is in executor memory.
If the executor Pod restarts, this state is lost.

5. The executor currently uses the `default` service account with RoleBinding in `default` namespace.
This is acceptable for the prototype, but should be replaced with a dedicated service account later.

6. Workflow event counts in `state_aggregator` reflect repeated demo runs.
This is expected because runs were repeated during validation.

7. The executor demo request still uses `vision-stage-runner:latest`.
For stronger reproducibility, pin this by digest or move stage image resolution to a config/catalog layer.

## Important operational notes

### Re-running the executor demo

The current demo request uses a fixed workflow id:
- `wf-exec-demo-001`

Repeated execution is valid, but it accumulates event history in `state_aggregator`.

### Port-forward used during validation

The executor API was validated through:

```bash
kubectl port-forward -n default service/workflow-executor 18002:8002
```

Then:

```bash
curl -sS -X POST http://127.0.0.1:18002/execute/workflow \
  -H 'content-type: application/json' \
  --data @/home/etri/jinuk/edge-orch/workflow_executor/k8s/demo-request.json
```

### Aggregator workflow state check

```bash
kubectl get --raw /api/v1/namespaces/default/services/http:state-aggregator:8000/proxy/state/workflows
```

### Prometheus target check

```bash
kubectl get --raw '/api/v1/namespaces/kube-system/services/http:prometheus-kube-prometheus-prometheus:9090/proxy/api/v1/targets?state=active'
```

## Recommended next steps

1. Replace synthetic `vision_stage_runner` stage specs with real stage container images and commands.

2. Move from per-request in-memory placement tracking to explicit persisted workflow execution state.

3. Add real `replan` flow:
- consult `placement/replan`
- compare current placement against latest node state
- decide whether next stage or a retried stage should move

4. Add explicit current workflow execution API to `workflow_executor`.
Examples:
- `GET /workflow/{workflow_id}`
- `GET /runs`

5. Introduce a dedicated `ServiceAccount` for `workflow_executor`.

6. Decide whether executor should stay synchronous or move to:
- async controller style
- CRD/operator style
- queue-backed workflow execution

7. Pin `vision-stage-runner` in the executor request by digest instead of `latest`.

8. Add a real overload scenario for experiments.
This is the missing step before stronger evaluation claims.

## Suggested short narrative for current milestone

Current repository state supports:
- monitoring reuse through Prometheus/node-exporter
- workflow event reporting
- normalized state aggregation
- heuristic stage placement
- actual Kubernetes stage execution from placement decisions
- mixed-architecture stage execution with a multi-arch stage image

This is now a working prototype of a workflow-aware, state-aware, heterogeneity-aware edge offloading control plane.
It is still an early prototype and not yet a full runtime migration system.
