# 프로덕션 전환 로드맵

`data-gaps-and-schema-risks.md`의 문제를 전제로, 우선순위 순으로 "뭘 붙여야 하는가".

## P0 — 이것 없이는 프로덕션이 아님

### 1. 영속화 싱크 — MVP 연결됨 (PROJ-28)
- ~~enrichment 뒤에 저장 스테이지를 붙인다~~ → **완료**: `src/enrichment/sink_clickhouse.py`가
  push 단위 배치로 ClickHouse `enriched_events`에 적재한다(mock 컨테이너, 실 저장소 구축 전).
- `record_id`가 결정적(idempotent)이라 **ReplacingMergeTree ORDER BY event_id** 로
  재시도·replay 중복이 공짜로 해결된다(조회는 `FINAL`).
- 남은 항목: 원본 아카이브(`data/{codex,claude_code}/*.jsonl`)를 읽어 같은 `process()`에
  흘리는 **backfill 스크립트** 한 개 (README에 이미 계획된 항목) — 장애 복구·스키마
  재정규화의 기반.

### 2. 오류 격리 (배치 전체 유실 차단)
- 레코드 단위 try/except: 깨진 레코드는 **DLQ 파일**(`data/deadletter/*.jsonl`)에 원문+오류를 남기고
  나머지는 정상 처리 후 200 응답.
- 요청 자체가 깨졌을 때만 400, 내부 오류는 **503**(collector가 재시도하도록)
  — RDS/ClickHouse 장애의 503 분류는 반영됨(`enrichment.errors.BackendUnavailable`);
  레코드 단위 DLQ 는 미구현.

### 3. collector 내구성
```yaml
extensions: [file_storage, health_check]
exporters:
  otlphttp/telemetry_pipeline:
    sending_queue: { storage: file_storage }   # 재시작에도 큐 생존
processors: [memory_limiter, redaction/secrets, batch]  # metrics에도 redaction 추가
```
- 이미지 태그 고정(`otel/opentelemetry-collector-contrib:0.x.y`), 파일 exporter 로테이션
  (`rotation:` 옵션) 추가.

### 4. 리시버를 진짜 서버로
- `http.server` → **FastAPI/uvicorn** (또는 collector를 아예 리시버 앞단으로 쓰고 gRPC 수신).
- 요청 크기 제한, gzip 해제 상한, 타임아웃, graceful shutdown(종료 시 처리 중 배치 flush).
- 컨테이너화(Dockerfile) + compose에 리시버 포함 → `host.docker.internal` 의존 제거.

## P1 — 데이터 신뢰성

### 5. 상태 있는 call_id 페어링
- push 단위 페어링을 버리고, **세션별 미결 승인 테이블**(TTL ~10분, 메모리 or SQLite)을 유지해
  push 경계를 넘는 decision↔call을 잇는다. 수락률 KPI의 전제 조건.

### 6. 격리(quarantine) 규칙
- `ts == 0.0`, `session_id == "(unknown)"` 레코드는 본 테이블 대신 격리 테이블로 + 진단 이벤트 발화.
  전 사용자 병합·정렬 오염을 원천 차단.

### 7. 신원·테넌트를 신뢰 경계에서 스탬핑
- collector에 인증(bearer/mTLS)을 붙이고, `tenant.id`는 클라이언트 속성이 아니라
  **인증 컨텍스트에서 collector가 주입**(`resource` processor + auth extension).
  현재 구조는 누구나 남의 tenant로 위장 가능.

### 8. 테스트 + CI
- 지금 테스트가 0개다. `data/{codex,claude_code}/*.jsonl`에 실데이터가 쌓이므로
  **골든 파일 테스트**부터:
  원시 push → 정규화 JSON 스냅샷 비교. 어댑터 회귀를 즉시 잡는다.
- `finalize()` 멱등성(같은 입력 → 같은 record_id) property 테스트.
- GitHub Actions로 lint(ruff) + 테스트. `.github/` 템플릿은 있는데 워크플로가 없다.

## P2 — 운영 가시성·완성도

### 9. 파이프라인 자체의 관측
- 리시버가 자기 메트릭을 노출: 수신/정규화/OTHER/진단 카운트, 처리 지연.
- 진단 스냅샷 생성(`python src/diagnostics/snapshot_cli.py`)을 크론 또는 대시보드로 —
  `mapping_miss` 비율이
  임계 초과하면 알림 (Codex to-spec 검증이 여기서 끝난다).
- 어댑터 미분기 이벤트(`LogKind.OTHER`)도 진단 이벤트를 발화하도록 수정 — 신규 이벤트 감지용.

### 10. 스키마 관리
- 삭제된 `SCHEMA.md`를 dataclass에서 **자동 생성**으로 부활 (수기 문서는 다시 썩는다).
- `SCHEMA_VERSION` 증가 시 마이그레이션 규칙 문서화. diagnostics 관찰 → 매핑 →
  adapter_version 증가 절차를 README에 명문화.

### 11. 가격표 운영
- `pricing.py` 하드코딩 → **버전·유효기간 있는 설정 파일**(`pricing.yaml`: model, effective_date, 단가).
  과거 데이터 재계산 시 당시 단가 적용이 가능해진다. placeholder 단가를 실제 가격표로 갱신.

### 12. 미완 어댑터 마무리
- `adapters/*/metrics.py`에 CC의 lines_of_code/commit/PR/active_time → 전용 이벤트 타입으로 승격
  (생산성 지표의 유일한 소스인데 현재 통과만 함. 승격 대상 payload 타입은 구현 시 정의).
- Codex 실데이터 흘려 diagnostics 확인 → 토큰 키명 확정, traces 스텁 구현.

## 붙이면 좋은 것 (선택)

- **패키징**: `pyproject.toml` + `src` 레이아웃 정리 (지금은 sys.path 의존 실행).
- **retention 정책**: 원본 아카이브·진단 로그 보존 기간과 삭제 잡.
- **PII 검토**: `user.email`·파일 경로·command는 개인정보 성격 — 보존 기간·접근 통제 정의.
- **대시보드**: 영속화가 생기면 Grafana/Metabase로 토큰·비용·수락률 롤업.

## 요약 순서

```
1주차:  P0-2 오류 격리 → P0-1 SQLite 싱크 + backfill → P0-3 collector 내구성
2주차:  P0-4 서버 교체·컨테이너화 → P1-8 골든 테스트 + CI
3주차~: P1-5 페어링 상태화, P1-6 격리, P1-7 인증/테넌트, P2 순차
```
