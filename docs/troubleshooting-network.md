# Troubleshooting: Node Network & EdgeMesh Recovery

This document records the resolution of network connectivity issues encountered after adding a new worker node (`etri-ser0002-cgnmsb`) to the cluster.

## 1. Problem Symptoms
- New node could not reach the Kubernetes API server (`10.96.0.1:443`).
- Cluster-wide DNS failure (I/O timeouts to `1.1.1.1`).
- EdgeMesh logs reported `peer id mismatch` and `failed to install iptables rule (physdev match missing)`.
- Infinite loop: Network setup failed due to DNS failure, and DNS failed because it was scheduled on the unconfigured new node.

## 2. Root Cause Analysis

### A. CoreDNS Circular Dependency
The scheduler placed a CoreDNS pod on the new node before its CNI (Flannel) and EdgeMesh configurations were finalized. Since other pods (like `cloud-iptables-manager`) depend on CoreDNS to find the API server, the node remained in an unconfigured state, unable to bootstrap itself.

### B. EdgeMesh Peer ID Mismatch
The `edgemesh-agent-cfg` ConfigMap contained an outdated Peer ID (`...ijb`) for the bootstrap relay. The actual relay server (`etri-ser0001-cg0msb`) was using a different ID (`...GgD`), causing security protocol negotiation failures.

### C. Host Kernel Configuration
The `br_netfilter` and `xt_physdev` kernel modules were not active on the new host, preventing EdgeMesh from installing necessary `iptables` rules for service intercept.

## 3. Resolution Steps

### Step 1: Recover Cluster DNS
To break the failure loop, CoreDNS was pinned to the stable control-plane node.
```bash
kubectl patch deployment coredns -n kube-system -p '{"spec": {"template": {"spec": {"nodeSelector": {"kubernetes.io/hostname": "etri-ser0001-cg0msb"}}}}}'
```

### Step 2: Fix EdgeMesh Configuration
Updated the `edgemesh-agent-cfg` ConfigMap with the correct relay node information and restarted the agent.
```bash
# Corrected relayNodes in edgemesh-agent-cfg to match actual server hostname and ID
kubectl rollout restart ds edgemesh-agent -n kubeedge
```

### Step 3: Configure Host Kernel
Manually enabled required modules and bridge settings on the new node (`192.168.0.5`).
```bash
sudo modprobe br_netfilter
sudo modprobe xt_physdev
sudo sysctl -w net.bridge.bridge-nf-call-iptables=1
sudo sysctl -w net.ipv4.ip_forward=1
```

## 4. Verification
- **Peer Connectivity**: EdgeMesh logs now show `New stream between peer ... success`.
- **DNS Resolution**: Internal and external DNS queries are succeeding from the new node.
- **Service Routing**: `iptables` rules are correctly installed, allowing traffic to flow through the gateway.

## 5. Prevention for Future Nodes
- **Node Pinning**: Keep critical infra (DNS, Registry) on stable cloud nodes.
- **Pre-flight Check**: Ensure `br_netfilter` is part of the node provisioning script.
- **Config Sync**: Verify EdgeMesh Peer IDs after any major relay server restart.
