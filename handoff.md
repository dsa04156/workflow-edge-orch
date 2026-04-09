# Handoff

## Current status

This repository now has eight working pieces connected end-to-end:

1. `state_aggregator`
2. `workflow_reporter`
3. `placement_engine`
4. `workflow_executor` (With SQLite persistence & Replanning)
5. `vision_stage_runner` (Multi-arch synthetic stage payload)
6. **GitHub Actions CI Pipeline** (Self-hosted multi-arch buildx)
7. **ArgoCD Image Updater** (Automated tag tracking & rollout)
8. **Traefik Gateway** (Standardized access via sslip.io)

The current system supports:
- Prometheus metric ingestion into `state_aggregator`
- Normalized node/workflow state exposure
- GitOps-driven deployment via ArgoCD
- Automated multi-arch container builds & registry pushes
- Automated deployment rollouts on image updates
- Heuristic placement & stage-boundary replanning
- Standardized domain access (`*.sslip.io`) without local hosts modification

## What was implemented

### 1. `state_aggregator`
- Periodic Prometheus polling & node metric normalization.
- Workflow event ingestion & summary state generation.
- `/metrics` endpoint for Prometheus scraping.

### 2. `workflow_executor`
- **SQLite Persistence**: Execution history and states are now persisted in `workflow_state.db`.
- **Replanning Hook**: refreshes placement via `placement_engine` `/placement/replan` before each stage.
- **Always Pull**: Enforced `imagePullPolicy: Always` for all dynamic Jobs.

### 3. `placement_engine`
- Heuristic stage placement logic (`/placement/decide`).
- Multi-stage replanning logic (`/placement/replan`).

### 4. CI/CD Infrastructure
- **GitHub Actions**: `.github/workflows/docker-build-push.yml` automates multi-arch builds (AMD64/ARM64) using host `buildx`.
- **ArgoCD Image Updater**: Tracks `latest` tag digests and triggers automated rollouts.
- **Traefik**: Acts as the main cluster entry point using `IngressRoute` CRDs.

### 5. `vision_stage_runner`
- Multi-arch image build for `linux/amd64` and `linux/arm64`.
- Reusable synthetic stage logic for the full vision pipeline.

## Images and Deployments

We have moved away from hardcoded digests to a **Tag-based Tracking** strategy.

- **Image Tag**: `latest`
- **Pull Policy**: `Always`
- **Automation**: ArgoCD Image Updater tracks registry changes and updates live deployments.

## Known Limitations

1. **Migration**: No live checkpoint-based migration; moves occur at stage boundaries.
2. **Synthetic Payload**: Stages currently run synthetic logic (hash loops) rather than real AI models.
3. **Registry**: Currently using basic Docker registry.

## Recommended next steps

1. **Data Persistence Layer**: Implement **Redis** or **MinIO** for sharing image data between stages.
2. **Real AI Integration**: Replace `vision_stage_runner` loops with actual ONNX/PyTorch inference code.
3. **Overload Scenarios**: Create experiment scripts to trigger intentional node/network stress for evaluation.

## Latest Updates (April 2026)
- **ArgoCD Cloud Node Pinning**: `argocd-server` is now pinned to cloud nodes (`environment=cloud`).
- **sslip.io Integration**: All web UIs (ArgoCD, Grafana, Prometheus) are accessible via `http://<service>.<ip>.sslip.io`.
- **CI/CD Automation**: Full E2E automation from `git push` to live deployment rollout is verified.
- **Cluster Expansion**: Added a new standard Kubernetes worker node (`etri-ser0002-cgnmsb`, `amd64`) to the cloud tier, increasing capacity for heavy AI inference and control plane redundancy.
