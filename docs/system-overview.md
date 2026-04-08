# System Overview

## 1. Project goal

This project targets a mixed-device edge AI environment composed of:
- one x86 server
- one Jetson edge AI device
- one Raspberry Pi 5 edge device

The goal is to build a runtime orchestration system that:
- splits AI services into workflow stages
- observes node state and workflow execution state
- places, migrates, or offloads stages dynamically
- optionally adds agent-assisted replanning later

This is not a generic cluster scheduler. It is a workflow-aware edge offloading controller.

---

## 2. Why this system is needed

The target environment is heterogeneous:
- different architectures: x86_64 vs aarch64
- different operating systems
- different kernels
- different memory capacities
- different accelerator availability

Because of this heterogeneity:
- static placement is inefficient
- one node can become a bottleneck while others are idle
- CPU/memory-only decisions are often insufficient
- AI services should not be treated as monolithic units

Instead, AI services should be split into stages such as:
- capture
- preprocess
- inference
- postprocess
- result delivery

Then the system should decide:
- which stage stays near the source device
- which stage moves to Jetson
- which stage moves to the server
- when a stage must be migrated because of overload or SLA risk

---

## 3. Existing components vs new components

### Already available
- KubeEdge / Kubernetes cluster
- Prometheus
- Grafana
- node-exporter

### Reused directly
Prometheus + node-exporter are reused as the node-level raw metric source.

Use them for:
- CPU
- memory
- network
- load average
- node up/down

### New components to implement
1. `state_aggregator`
2. `workflow_reporter`
3. `placement_engine`
4. `agent_assisted_planner` (later)

---

## 4. High-level architecture

### A. Prometheus / node-exporter
Provides node-level raw metrics.

### B. workflow_reporter
Reports workflow/stage runtime events.

### C. state_aggregator
Combines:
- node-level metrics from Prometheus
- workflow events from workflow_reporter

Produces:
- node state
- workflow state
- normalized state
- scheduler/planner summary

### D. placement_engine
Uses:
- node profile
- current runtime state
- stage metadata

Returns:
- keep / migrate / offload decisions

### E. agent-assisted planner
Optional later layer.
Only helps when replanning is needed.

---

## 5. Key design principles

1. Reuse Prometheus for node metrics
2. Build a separate control-plane state layer
3. Treat AI services as workflow stages, not monoliths
4. Make placement decisions with heuristic logic first
5. Add agent-assisted planning only later
6. Keep monitoring path and control path separate

---

## 6. Main data sources

### Node-level raw metrics
From Prometheus / node-exporter:
- CPU usage
- memory usage
- load average
- network RX/TX
- node up/down

### Workflow-level events
From workflow_reporter:
- stage_start
- stage_end
- migration_event
- workflow_end
- failure_event

---

## 7. Main outputs of the system

### For the scheduler
- normalized node state
- workflow urgency
- SLA risk
- placement stability

### For humans
- Grafana dashboards
- raw JSONL logs
- experiment results

---

## 8. Implementation sequence

1. Build `state_aggregator`
2. Build `workflow_reporter`
3. Build `placement_engine`
4. Connect one real workflow
5. Add agent-assisted planning