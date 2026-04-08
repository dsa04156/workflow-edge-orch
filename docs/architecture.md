# Architecture

## 1. Nodes and roles

### Server node
- hostname: `etri-ser0001-CG0MSB`
- role: `cloud_server`
- preferred for:
  - heavy inference
  - centralized state aggregation
  - placement engine
  - planner candidate

### Jetson node
- hostname: `etri-dev0001-jetorn`
- role: `edge_ai_device`
- preferred for:
  - edge inference
  - preprocess
  - latency-sensitive stages

### Raspberry Pi 5 node
- hostname: `etri-dev0002-raspi5`
- role: `edge_light_device`
- preferred for:
  - capture
  - preprocessing
  - sensor ingestion
  - lightweight postprocess

---

## 2. Node profile schema

Each node should be represented by a fixed capability profile.

Example fields:
- `hostname`
- `node_type`
- `arch`
- `compute_class`
- `memory_class`
- `accelerator_type`
- `runtime_role`
- `preferred_workload`
- `risky_workload`

Example:

```json
{
  "hostname": "etri-dev0001-jetorn",
  "node_type": "edge_ai_device",
  "arch": "aarch64",
  "compute_class": "medium",
  "memory_class": "low",
  "accelerator_type": "gpu_embedded",
  "runtime_role": ["inference_candidate", "edge_processing_candidate"],
  "preferred_workload": ["edge_inference", "preprocess", "latency_sensitive_stage"],
  "risky_workload": ["large_model_serving", "many_concurrent_workflows", "central_planner"]
}

3. state_aggregator
Purpose

Central state hub that:

reads node metrics from Prometheus
receives workflow/stage events
builds normalized orchestration state
exposes lightweight APIs for placement logic
Deployment
Kubernetes Deployment
server node preferred
Inputs
A. From Prometheus

Minimum queries:

node health (up)
CPU utilization
memory usage ratio
load average
network RX/TX rate
B. From workflow_reporter

Minimum events:

stage_start
stage_end
migration_event
workflow_end
failure_event
Outputs

Must provide:

GET /state/nodes
GET /state/node/{hostname}
GET /state/workflows
GET /state/workflow/{workflow_id}
GET /state/summary
Internal storage

Initial version:

latest state in memory
raw logs in JSONL

Suggested files:

data/node_state.jsonl
data/workflow_event.jsonl
instance mapping

Prometheus instance values must be mapped to logical hostnames via config file.

Suggested path:

app/config/instance_map.json
4. workflow_reporter
Purpose

Emit workflow and stage execution events to the aggregator.

Form

Initial version should be a Python helper module.

Minimum helper functions
report_stage_start(...)
report_stage_end(...)
report_migration(...)
report_failure(...)
Destination
POST /workflow-event
Minimum event fields
event_type
timestamp
workflow_id
workflow_type
stage_id
stage_type
assigned_node

Optional fields:

exec_time_ms
queue_wait_ms
transfer_time_ms
from_node
to_node
reason
status
5. placement_engine
Purpose

Decide where a workflow stage should run.

Form

Initial version should be a Python module, not a full service.

Inputs
node profile
current node state
workflow stage metadata
current placement
Outputs

Decision object:

workflow_id
stage_id
target_node
decision_reason
action_type

action_type can be:

keep
migrate
offload_to_cloud
reject
Initial decision rules
heavy inference -> server preferred
source-near stage -> Raspberry Pi preferred
GPU-required stage -> server or Jetson only
high memory pressure node -> do not assign new heavy stages
unavailable node -> never place
overload -> suggest sibling edge redistribution or cloud offload
Initial implementation style
heuristic / weighted score only
no RL
no LLM
6. Normalized state model
Node-level normalized state
compute_pressure: low / medium / high
memory_pressure: low / medium / high
network_pressure: low / medium / high
node_health: healthy / degraded / unavailable
Workflow-level normalized state
workflow_urgency
sla_risk
placement_stability

These states are created inside state_aggregator.

7. Monitoring path vs control path
Monitoring path
Prometheus
Grafana
raw JSONL logs
Control path
state_aggregator APIs
placement_engine
later: agent-assisted planner

Prometheus/Grafana are not the control plane.
They are monitoring infrastructure.

8. What not to build first

Do not build first:

custom node collector replacing Prometheus
full HA storage
RL-based scheduler
full LLM-based orchestration
generic Kubernetes scheduler replacement

---

## 4) `docs/experiments.md`

```md
# Experiments

## 1. Evaluation goal

The evaluation should show that a workflow-aware, state-aware, heterogeneity-aware orchestration layer can improve runtime behavior in a mixed-device edge environment.

The target outcomes are:
- lower end-to-end latency
- lower p95/p99 latency
- better resource utilization
- more stable placement under changing conditions
- reasonable migration overhead

---

## 2. Target workload

Start with exactly one real workflow.

Recommended first options:
1. vision inference pipeline
2. sensor/time-series anomaly detection pipeline

Preferred starting point:
- one workflow only
- 3 to 5 stages

Example workflow:
- capture
- preprocess
- inference
- postprocess
- result delivery

---

## 3. Baselines

Prepare the following baselines:

### Baseline A: static placement
- fixed stage placement
- no runtime migration
- no replanning

### Baseline B: heuristic placement only
- placement by fixed rules
- no runtime replanning

### Baseline C: heuristic placement + replanning
- runtime migration allowed
- no agent-assisted planning

### Proposed later: heuristic + agent-assisted planning
- planner only when replanning is needed

---

## 4. Metrics to collect

### Node-level
- CPU utilization
- memory usage ratio
- load average
- network receive/transmit rate
- node availability

### Workflow-level
- stage execution time
- stage queue wait time
- stage transfer time
- end-to-end latency
- migration count
- failure count
- SLA violation count

### System-level
- average latency
- p95 latency
- p99 latency
- makespan
- throughput
- resource utilization
- migration overhead
- recovery time

---

## 5. Experiment scenarios

### Scenario 1: normal workload
Goal:
- verify baseline behavior
- ensure all stages run correctly

### Scenario 2: burst workload
Goal:
- evaluate whether overload is detected
- evaluate whether migration/offloading helps

### Scenario 3: specific node overload
Goal:
- overload one node intentionally
- verify replanning logic

### Scenario 4: network bottleneck
Goal:
- reduce effective network quality
- evaluate if source-near or alternative placement becomes better

### Scenario 5: node failure or degraded performance
Goal:
- observe recovery or fallback behavior
- verify unavailable node handling

---

## 6. Required logs

Store the following for every experiment:
- workflow start time
- workflow end time
- stage start/end events
- migration events
- planner-related events (later)
- node-level utilization snapshots
- experiment configuration
- timestamps for all records

Suggested format:
- JSONL
- CSV for summary tables

Suggested file layout:
- `logs/<experiment-id>/node_state.jsonl`
- `logs/<experiment-id>/workflow_event.jsonl`
- `logs/<experiment-id>/config.json`

---

## 7. What to prove in the first milestone

The first milestone does not need to prove full agent-assisted orchestration.

It only needs to prove:
1. node state can be read reliably from Prometheus
2. workflow events can be captured reliably
3. node state + workflow state can be merged
4. normalized orchestration state can be generated
5. a simple heuristic placement decision can be made from that state

---

## 8. Later planner evaluation

When the agent-assisted planner is added later, evaluate:

- number of planner calls
- planner latency
- planner acceptance/rejection rate
- whether planner suggestions improve p95 latency or stability
- whether planner overhead is justified

Planner evaluation is not required for the first implementation milestone.

---

## 9. Reviewer-facing positioning

### What to claim
- workflow-aware orchestration
- state-aware offloading
- heterogeneity-aware runtime control
- practical mixed-device edge orchestration

### What not to overclaim
- do not claim a full autonomous agentic system
- do not claim a replacement for Prometheus/Grafana
- do not claim a replacement for generic Kubernetes scheduling
- do not claim RL or LLM necessity in the first milestone