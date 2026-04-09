# AGENTS.md

## Project overview
This repository is for a mixed-device edge AI orchestration system on a KubeEdge-based cluster.

Target environment:
- x86 server node
- Jetson edge AI device
- Raspberry Pi 5 edge device

Goal:
- split AI services into workflow stages
- observe node/runtime state
- place/migrate/offload stages dynamically
- add agent-assisted planning only as the last step

This project is **not** a generic cluster scheduler. It is a **workflow-aware edge offloading control plane**.

---

## Current implementation status (April 2026)

### ✅ Completed Milestones
1.  **State Aggregator & Monitoring**:
    - Central hub for Prometheus metrics and workflow events implemented.
    - Normalized state exposure for nodes and workflows.
2.  **GitOps & Continuous Deployment**:
    - **ArgoCD Integration**: Automatic synchronization of control plane components.
    - **ArgoCD Image Updater**: Automated rollout of new versions based on image digest changes.
3.  **CI/CD Pipeline**:
    - **GitHub Actions**: Automated multi-architecture builds (AMD64/ARM64) using `docker buildx`.
    - **Self-hosted Runner**: Integration with local build environments and registries.
4.  **Workflow Executor Improvements**:
    - **Persistence**: Added SQLite-based state storage for workflow history.
    - **Reliability**: Forced `image_pull_policy: Always` for dynamic Jobs to ensure latest AI code execution.
5.  **Heuristic Placement Engine**:
    - Weighted score-based placement logic for 이기종(Heterogeneous) environments.

### 🚀 In Progress / Next Steps
1.  **Registry Direction**: Keep the existing Docker registry as the active registry solution for now.
    Harbor-related work is exploratory only and must not replace the current registry unless explicitly requested.
2.  **Real AI Integration**: Replacing synthetic stages with actual Vision/Inference workloads.
3.  **Data Persistence Layer**: Implementing shared storage (Redis/MinIO) for inter-stage data passing.
4.  **Re-planning Logic**: Implementing dynamic migration during workflow execution based on live node state.

---

## Core implementation principles

### Reuse existing monitoring
Do **not** rebuild basic node monitoring from scratch.

Already available and should be reused:
- Prometheus
- Grafana
- node-exporter

Use Prometheus + node-exporter as the source of node-level raw metrics:
- CPU
- memory
- network
- load average
- node up/down

Do not introduce a separate host-level `node_monitor.py` as the primary data source unless a truly missing custom metric is required later.

### Build the control plane
The main components to implement are:

1. `state_aggregator`
   - reads node-level metrics from Prometheus
   - receives workflow/stage events
   - builds normalized state
   - exposes lightweight APIs for scheduler/planner

2. `workflow_reporter`
   - emits workflow/stage execution events
   - reports stage_start, stage_end, migration_event, failure_event

3. `placement_engine`
   - heuristic/score-based stage placement and replanning
   - uses node profile + runtime state + stage metadata

4. `agent_assisted_planner` (later)
   - not part of the first implementation milestone
   - only assists when replanning is needed

---

## Current node roles

### Server
- hostname: `etri-ser0001-CG0MSB`
- role: `cloud_server`
- preferred for:
  - heavy inference
  - centralized state aggregation
  - placement engine
  - planner candidate

### Jetson
- hostname: `etri-dev0001-jetorn`
- role: `edge_ai_device`
- preferred for:
  - edge inference
  - preprocess
  - latency-sensitive stages

### Raspberry Pi 5
- hostname: `etri-dev0002-raspi5`
- role: `edge_light_device`
- preferred for:
  - capture
  - preprocessing
  - sensor ingestion
  - lightweight postprocess

---

## Architecture constraints

### `state_aggregator`
- implement in Python
- prefer FastAPI
- deploy as Kubernetes Deployment
- place on server node if node affinity is used
- store latest state in memory
- append raw event logs to JSONL
- no Redis/Postgres/complex DB for the first version

### `workflow_reporter`
- implement as a Python helper/module first
- use HTTP POST to aggregator
- keep the event schema explicit and small

### `placement_engine`
- implement as a Python module first
- do not use RL or LLM in the initial version
- start with heuristic / score-based rules only

---

## What not to do
Do not:
- replace Prometheus/Grafana
- build a generic Kubernetes scheduler
- introduce RL as the first control logic
- let an LLM directly control all scheduling decisions
- add distributed storage or high-availability first
- over-engineer authentication/authorization in early prototypes

---

## Implementation order
Follow this order strictly:

1. `state_aggregator`
2. `workflow_reporter`
3. `placement_engine`
4. one real workflow integration
5. agent-assisted planning layer

---

## Coding style
- Keep components minimal and testable
- Prefer explicit schemas over implicit dicts
- Return decision reasons from placement logic
- Separate raw metrics from normalized state
- Separate monitoring path from control path

---

## Expected APIs

### `state_aggregator`
Must provide:
- `POST /workflow-event`
- `GET /state/nodes`
- `GET /state/node/{hostname}`
- `GET /state/workflows`
- `GET /state/workflow/{workflow_id}`
- `GET /state/summary`

### `workflow_reporter`
Must be able to emit:
- `stage_start`
- `stage_end`
- `migration_event`
- `workflow_end`
- `failure_event`

---

## Prometheus usage
Use Prometheus HTTP API as the source of node-level metrics.

Minimum queries:
- node health (`up`)
- CPU utilization
- memory usage ratio
- load average
- network receive/transmit rate

Maintain an explicit `instance -> hostname` mapping file in the aggregator config.

---

## Research framing
The system should be described as:
- workflow-aware
- state-aware
- heterogeneity-aware
- dynamic offloading / runtime orchestration

The system should **not** be framed as:
- a full agentic AI system
- a full replacement for Kubernetes scheduling
- a replacement for Prometheus/Grafana