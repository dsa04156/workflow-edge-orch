# 장애 조치: 노드 네트워크 및 EdgeMesh 복구 가이드

이 문서는 새로운 워커 노드(`etri-ser0002-cgnmsb`) 추가 후 발생한 네트워크 연결성 문제와 그 해결 과정을 기록합니다.

## 1. 장애 증상
- 새로운 노드에서 쿠버네티스 API 서버(`10.96.0.1:443`) 접속 불가.
- 클러스터 전체 DNS 장애 발생 (`1.1.1.1` 등으로의 I/O 타임아웃).
- EdgeMesh 로그에 `peer id mismatch` 및 `failed to install iptables rule (physdev match missing)` 에러 발생.
- **무한 루프:** DNS 장애로 인해 네트워크 설정이 실패하고, 네트워크 설정이 안 된 새 노드에 DNS가 배치되어 DNS가 계속 실패하는 상황 발생.

## 2. 원인 분석

### A. CoreDNS 순환 의존성 문제
쿠버네티스 스케줄러가 네트워크 설정(CNI, EdgeMesh)이 아직 완료되지 않은 새 노드에 CoreDNS 팟을 배치했습니다. 노드 관리 팟(`cloud-iptables-manager`)들이 API 서버를 찾기 위해 CoreDNS에 의존하는데, CoreDNS 자체가 먹통인 노드에 떠 있으면서 노드가 스스로를 설정하지 못하는 상태에 빠졌습니다.

### B. EdgeMesh Peer ID 불일치
`edgemesh-agent-cfg` ConfigMap에 부트스트랩용 Relay 노드 ID가 예전 값(`...ijb`)으로 고정되어 있었습니다. 실제 Relay 서버(`etri-ser0001-cg0msb`)는 다른 ID(`...GgD`)를 사용 중이었기 때문에 보안 프로토콜 협상 과정에서 연결이 거부되었습니다.

### C. 호스트 커널 설정 미비
새로운 호스트 서버에 `br_netfilter` 및 `xt_physdev` 커널 모듈이 활성화되지 않았습니다. 이로 인해 EdgeMesh가 서비스 트래픽 가로채기를 위해 필요한 `iptables` 규칙을 심는 데 실패했습니다.

## 3. 해결 단계

### 1단계: 클러스터 DNS 복구
장애 루프를 끊기 위해 모든 CoreDNS 팟을 안정적인 클라우드 제어 노드로 강제 고정(Pinning)했습니다.
```bash
kubectl patch deployment coredns -n kube-system -p '{"spec": {"template": {"spec": {"nodeSelector": {"kubernetes.io/hostname": "etri-ser0001-cg0msb"}}}}}'
```

### 2단계: EdgeMesh 설정 수정
`edgemesh-agent-cfg` ConfigMap을 실제 서버의 호스트네임과 피어 ID에 맞게 수정하고 에이전트를 재시작했습니다.
```bash
# edgemesh-agent-cfg의 relayNodes 정보를 실제 서버 정보로 수정 후 재시작
kubectl rollout restart ds edgemesh-agent -n kubeedge
```

### 3단계: 호스트 커널 설정
새 노드(`192.168.0.5`)에서 필요한 모듈을 로드하고 브릿지 설정을 활성화했습니다.
```bash
sudo modprobe br_netfilter
sudo modprobe xt_physdev
sudo sysctl -w net.bridge.bridge-nf-call-iptables=1
sudo sysctl -w net.ipv4.ip_forward=1
```

## 4. 최종 검증
- **피어 연결:** EdgeMesh 로그에서 `New stream between peer ... success` 확인.
- **DNS 해석:** 새 노드에서 내부/외부 DNS 조회가 정상적으로 수행됨 확인.
- **서비스 라우팅:** `iptables` 규칙이 정상 설치되어 게이트웨이를 통한 트래픽 흐름 확인.

## 5. 향후 예방 조치
- **노드 고정:** DNS, 레지스트리 등 핵심 인프라는 항상 안정적인 클라우드 노드에 배치.
- **사전 점검:** 노드 추가 시 `br_netfilter` 등 필수 커널 설정이 포함된 프로비저닝 스크립트 사용.
- **설정 동기화:** Relay 서버 재시작 시 EdgeMesh 피어 ID 변경 여부를 반드시 확인.
