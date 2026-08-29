# ai-telemetry-pipeline — OTLP 인증·정규화·적재 파이프라인

CLI 코딩 툴(Claude Code / Codex …)이 보내는 OTLP 텔레메트리를 받아 **토큰을 검증하고,
벤더별 스키마를 공통 스키마로 정규화하고, 조직 정보를 결합해 ClickHouse 에 적재**한다.
**프롬프트 원문은 다루지 않는다** — 정규화 스키마의 `Prompt` payload 는 길이와 명령 이름만 싣는다
(`docs/normalizer.md`).

앱이 둘이다.

| | 스택 | 하는 일 |
|---|---|---|
| `apps/auth-proxy` | Node / TypeScript | Bearer 토큰 검증 → `x-pulsemetry-*` 신원 헤더 4종 부여 → Collector 로 전달 |
| `apps/telemetry-processor` | Python | 신원 헤더 판독 → 벤더 어댑터 정규화 → 조직 결합 → ClickHouse 적재 |

## 데이터 흐름

```
CLI 툴 ──OTLP/HTTP──▶ auth-proxy ──▶ collector ──┬─ file exporter ▶ data/{codex,claude_code}/*.jsonl
        (Bearer 토큰)    (:4316)      (:4318)     │                  (제품별 원본 아카이브, 보존용)
                         토큰 검증                 └─ otlphttp(json) ▶ telemetry-processor (:8080)
                         신원 헤더 4종                                  normalize ▶ enrichment ▶ ClickHouse
                                                                                          (enriched_events)
```

- **auth-proxy** — 토큰을 `TOKEN_HASH_SECRET` 으로 HMAC-SHA256 해시해
  `enrollment.telemetry_tokens` 에서 조회한다. 연결된 installation·member·tenant 가 모두 활성일 때만
  통과시키고, `x-pulsemetry-token-id` · `-tenant-id` · `-installation-id` · `-member-id` 를 붙인다.
- **신원 전파** — collector 의 `include_metadata` · `headers_setter` · `batch.metadata_keys` 세 설정이
  그 4개 헤더를 배치 경계 너머로 보존한다. 셋 중 하나라도 빠지면 ClickHouse 의
  `tenant_id` · `installation_id` 가 빈 문자열이 된다. **이 레포의 `otel-collector-config.yaml` 과
  `infra/config/otel-collector.yaml` 은 같은 값을 유지해야 한다** — 배포 설정의 소유는 `infra` 다.
- **원본 아카이브** — collector 가 resource 의 `service.name` 을 기준으로 제품별 파일에 append 한다.
  아카이브에서 backfill 하는 리더는 지금 없다.
- 리시버가 잠깐 죽거나 RDS/ClickHouse 장애로 503 을 돌려줘도 collector 의 재시도 큐가 흡수한다 —
  단 큐는 메모리 큐라서 collector 프로세스가 살아 있고 큐가 차지 않은 동안만이다(`docs/data-gaps-and-schema-risks.md` §1.3).

## 실행

```bash
docker compose -f docker-compose.dev.yml up -d
```

compose 가 5개 서비스를 올린다 — `auth-proxy` · `telemetry-processor` · `otel-collector` ·
`postgres`(mock RDS) · `clickhouse`(mock 적재 타깃).

- `postgres` 는 최초 초기화 시 `sql/rds/` 의 스키마와 시드를 자동 적용한다.
- ClickHouse DDL(`sql/clickhouse/schema.sql`)은 `telemetry-processor` 가 기동 시 멱등 적용한다.
- 볼륨이 없으므로 `down` 후 `up` 마다 스키마와 시드가 재적용된다(결정론적 리셋).

`sql/rds/` 는 **dev 부트스트랩 편의용이지 진실원이 아니다.** `enrollment` 스키마의 진실원은
`pulsemetry-backend` 의 Flyway 마이그레이션이고, 이 레포는 그 스키마의 **읽기 전용 소비자**다.

빌드·검사:

```bash
cd apps/auth-proxy && npm ci && npm run typecheck && npm run build   # CI 가 도는 것도 이것뿐
cd apps/telemetry-processor && pip install -r requirements.txt
```

**레포에 자동화된 테스트가 없다.** CI 는 auth-proxy 의 typecheck/build 만 돈다.
변경할 때는 수동 검증이 필요하다.

## 구조

```
apps/
  auth-proxy/               TypeScript. OTLP 인증 프록시 (README 는 앱 디렉토리 안에)
  telemetry-processor/
    otlp_receiver.py          OTLP/HTTP 진입점. 신원 헤더 4종을 여기서 읽는다 (--host/--port)
    processor.py              normalize → enrich 스트림 조립
    diagnostics/              누락·정합성 인메모리 집계 및 JSON 스냅샷 (snapshot_cli.py)
    normalizer/
      normalize.py              OTLP push 한 건 → Iterator[Normalized]
      pricing.py                토큰 기반 비용 추정 (단가는 자리표시자)
      model/                    공통 스키마 (enums + 신호별 메시지). 순수 데이터
      otlp/                     OTLP 파싱 공용 유틸 (툴 무관). readers.py = 3 시그널 리더
      common/                   context · envelope · call_id · metric · serialization
      adapters/                 플랫폼 × 시그널. 새 어댑터는 normalize 에 등록
        claude_code/              common.py + logs.py + metrics.py + traces.py
        codex/                    common.py + logs.py + metrics.py + traces.py
    enrichment/               normalize 이후·저장 이전 스테이지 (processor 컨테이너 인프로세스)
      enrich.py                 push 단위 오케스트레이션: Iterable[Normalized] → list[Enriched]
      model.py                  Enriched — Normalized 를 감싸고 파생 필드를 쌓는 컨테이너
      errors.py                 enrichment 단계 예외
      sink_clickhouse.py        ClickHouse HTTP 적재 (stdlib urllib, JSONEachRow)
      providers/                EnrichmentProvider ABC + 자동발견 registry
        org.py                    팀 as-of 매핑 — RDS 조회로 team_ids_as_of 를 채운다
        github.py · jira.py · ai_analysis.py    no-op 스텁
otel-collector-config.yaml  ★ dev(in-repo) collector 설정. 배포 설정은 infra 소유
sql/rds/ · sql/clickhouse/  dev 부트스트랩 DDL·시드 (진실원 아님)
data/                       제품별 원본 아카이브 (compose bind mount)
```

전체 처리 진입점은 `apps/telemetry-processor/processor.py` 의 `process(doc)` 다. 내부에서
`normalize(doc)` 가 만든 `Normalized` 스트림에 `enrich(events)` 를 적용해 `list[Enriched]` 를
반환하고, 리시버가 이를 ClickHouse 에 배치 적재한다. 정규화기는 `call_id` 페어링을 위해 OTLP push
한 건을 내부 버퍼링하며, enrichment 도 같은 push 단위로 RDS 연결을 열고 닫는다.

새 외부 의존성(GitHub / Jira / AI 분석)은 `enrichment/providers/` 에 파일 하나를 추가하는 것만으로
registry 에 자동 등록된다(코어 수정 0). provider 산출물은 공통 컬럼으로 승격하지 않고
`enrichment_json` 으로만 적재한다 — org 만 whitelist 컬럼을 채우는 예외다.

## 정규화 모델

**Normalized{Log,Span,Metric}** = `normalizer/model/` 의 신호별 스키마. 셋이 공통 **`Envelope`**
(`identity` / `client` / `session_id` / `timestamp` / `record_id` / `_ingest`)를 품고, 신호별 상관 필드와
payload 만 각자 갖는다:

- `NormalizedLog` — `turn_id` / `call_id` / `sequence` + payload(`Prompt` · `LlmCall` · `LlmResponse` ·
  `ToolCall` · `ToolDecision` · `Lifecycle`)
- `NormalizedSpan` — `trace_id` / `span_id` / `parent_id` / `call_id` / `span_role` + payload(타이밍만;
  토큰·비용은 로그가 싣는다)
- `NormalizedMetric` — `MetricPoint`(name / value / unit / type / temporality / attrs)

필드 단위 정의는 `docs/normalizer.md` 가 진실원이다.

조인은 병합이 아니라 **다운스트림 group-by** 로 한다: LLM 은 `request_id`, 툴은 `call_id`,
그 위는 `session_id`. 신호 간 집계는 반드시 한 종류(`logs` 등)만 세어 이중계산을 피한다.

지원 툴: **Claude Code**(`claude_code.*`) · **Codex**(`codex.*`).

### 이 모델에서 꼭 지켜야 할 3가지

1. **값이 없으면 0 이 아니라 `None`.** "0건" 과 "측정 불가" 는 다른 사실이다.
   Codex 는 커밋/PR/라인을 *측정할 수 없다* — 0 으로 채우면 대시보드가 거짓말을 한다.
2. **토큰 합산은 `Tokens.billable`(input + output + cache_read + cache_create)로만.**
   `reasoning`(Codex reasoning_output, Gemini thoughts)과 `tool`(Gemini)은 `output` 의 부분집합일 수
   있어 더하면 이중계산이다. `total_reported` 는 검산 전용이다.
3. **`call_id` 는 조인 키다.** Claude Code 는 `tool_use_id` 를 그대로 옮기고, 없으면 합성으로 복구한다.
   Codex 는 대응 키가 없어 항상 합성한다(`_ingest.call_id_inferred=True`). `pair_call_ids()` 가 세션 내
   "같은 도구명의 직전 미결 승인" 과 짝지어 tool_decision ↔ tool_call 을 잇는다. 수락률 KPI 가 이 조인에 걸려 있다.

## 한계 (설계상 감수 또는 미완)

- **Codex 토큰 키명은 to-spec** — 공식 문서 스키마 기준이라 실데이터로 재확인이 필요하다.
  확인 방법은 실데이터를 흘린 뒤 diagnostics 의 `unmapped_fields` 집계를 보는 것이다.
- **`normalizer/pricing.py` 단가는 자리표시자다.** 실제 가격표로 갱신해야 한다.
- **메트릭 payload 승격이 없다.** 어댑터(`adapters/*/metrics.py`)는 구현돼 있지만 산출물이 범용
  `MetricPoint` 라, Claude Code 의 라인/커밋/PR/active_time(메트릭에만 존재)이 전용 payload 타입으로
  올라오지 않는다. 생산성 지표를 쓰려면 승격 대상 payload 타입을 먼저 정의해야 한다.
- **Codex 는 `turn_id` 가 없다** — 턴 경계를 정확히 잡을 수 없다. Claude Code 는 `prompt.id` 로
  잡을 수 있지만 아직 활용하지 않는다.
- 원문을 다루지 않으므로 "의도(why)" 의 세밀한 라벨은 이 단계에서 만들 수 없다.

## 이 레포가 소유하지 않는 것

- **토큰 발급** — `pulsemetry-backend`. 이 레포는 검증만 한다.
- **`enrollment` 스키마 DDL 의 진실원** — `pulsemetry-backend` 의 Flyway.
- 이 레포를 backend 로 통째 병합하는 제안(backend ADR 0006)은 **기각됐다** — 레포 2개 체제 유지.
  단 collector 는 backend 로 이관 예정이다(backend ADR 0007).
- **배포 collector 설정과 모든 AWS 리소스** — `infra`.
- 세션을 세부작업으로 분해하고 토큰을 귀속시키는 **분석·리포트 계층** — 이 레포 범위 밖이다.
  적재된 `enriched_events` 를 읽는 다운스트림이 맡는다.

레포 간 계약은 `../docs/contracts/telemetry-ingest.md` 가 단일 출처다.
소유 경계는 `../docs/architecture/repos.md` 를 본다.
