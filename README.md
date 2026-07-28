# 세부작업 분류 + 토큰 귀속 분석기 (메타데이터-only, 멀티툴)

CLI 코딩 툴(Claude Code / Codex …)의 OTLP 텔레메트리를 읽어 **세션을 세부작업으로 분해**하고
각 세부작업의 **토큰/비용을 귀속**시킨다. **프롬프트 원문은 사용하지 않는다** (메타데이터-only).

## 데이터 흐름

```
CLI 툴 ──OTLP──▶ collector ──┬─ file/{logs,metrics,traces} ▶ data/{codex,claude_code}/*.jsonl
                             │                               (제품별 원본 아카이브)
                             └─ otlphttp(json)             ▶ normalize ▶ enrichment ▶ ClickHouse
                                                             (otlp_receiver.py, 실시간 스키마)   (enriched_events)
```

- **원본 아카이브** `data/{codex,claude_code}/{logs,metrics,traces}.jsonl` — collector가
  resource의 `service.name`을 기준으로 제품별 파일에 append. 보존용.
- **처리 스트림** — collector가 `otlphttp`(encoding: json)로 push한 OTLP를
  `src/otlp_receiver.py`가 받아 정규화한 뒤 enrichment(조직/부서/사원 as-of 매핑)를 적용하고,
  push 단위 배치로 ClickHouse `enriched_events`에 적재한다(멱등: `record_id` +
  ReplacingMergeTree). 조직 정보 RDS와 ClickHouse는 실구축 전이라 compose의
  mock 컨테이너(postgres, clickhouse)가 대역이다.
- 리시버가 잠깐 죽거나 RDS/ClickHouse 장애로 503을 돌려줘도 collector의 재시도 큐가
  흡수한다. (원본 아카이브에서 backfill 하는 리더는 현재 없다 — 필요해지면 `pipeline`을
  파일에 돌리는 짧은 스크립트로 붙인다.)

## 실행

```bash
docker compose -f docker-compose.dev.yml up --build
```

compose 가 4개 서비스를 올린다: `processor`(리시버+enrichment, `requirements.txt`의
psycopg 필요), `otel-collector`, `postgres`(mock RDS — 조직 스키마+시드를
`src/enrichment/sql/rds/`에서 최초 초기화 시 자동 적용), `clickhouse`(mock 적재 타깃 —
DDL 은 processor 가 기동 시 멱등 적용: `src/enrichment/sql/clickhouse/schema.sql`).
볼륨이 없으므로 `down` 후 `up` 마다 스키마+시드가 재적용된다(결정론적 리셋).

단위 테스트(호스트에 3.13 이 없으면 컨테이너로):

```bash
docker run --rm -v "$PWD:/work" -w /work -e PYTHONPATH=src python:3.13-slim \
  python -m unittest discover -s tests -t .
```

정규화 출력은 한 줄에 `Normalized{Log,Span,Metric}` 하나이며 enum은 문자열, 관측되지 않은 값은 `null`,
공통 봉투는 `envelope`에 중첩되고 payload는 이벤트 종류에 맞는 중첩 JSON 객체로 기록된다.

옵션:
- `--idle-gap SEC`  : 유휴 간격이 이보다 크면 새 세부작업 (기본 240)
- `--json PATH`     : 리포트 JSON 저장
- `--teams PATH`    : 이메일→팀 매핑 파일 (기본 `teams.json`)
- `--history PATH`  : 추세 스냅샷 파일 (기본 `analysis/history.jsonl`)
- `--no-history`    : 추세 스냅샷을 기록하지 않음 (테스트/CI용)

## 구조 (스트림 처리)

```
src/
  otlp_receiver.py        OTLP/HTTP 진입점
  processor.py            normalize → enrich 스트림 조립
  diagnostics/            누락·정합성 인메모리 집계 및 JSON 스냅샷
  normalizer/             원시 OTLP → Normalized{Log,Span,Metric} 정규화 패키지
  model/                  공통 스키마 (enums + 메시지). 순수 데이터
  otlp/                   OTLP 파싱 공용 유틸 (툴 무관). readers.py = 3 시그널 리더
  common/                 context, envelope, call_id, metric, serialization 공통 로직
  adapters/               플랫폼 × 시그널. 새 어댑터는 normalize에 등록
    claude_code/            common.py + logs.py + metrics.py + traces.py
    codex/                  common.py + logs.py + metrics.py + traces.py
  normalize.py            OTLP push 한 건 → Iterator[Normalized]
  pricing.py              토큰 기반 비용 추정
  enrichment/             normalize 이후·저장 이전 스테이지 (processor 컨테이너 인프로세스)
    enrich.py             push 단위 오케스트레이션: Iterable[Normalized] → list[Enriched]
    model.py              Enriched — Normalized 를 감싸고 파생 필드를 쌓는 컨테이너
    resolve_employee.py   P4: 정본 신원(user_id) → RDS employee 해석(id-or-email)
    enrich_org.py         P5: 회사/부서/사원 as-of 매핑 ((unassigned) 폴백)
    providers/            P6: EnrichmentProvider ABC + 자동발견 registry
                          (org 레퍼런스, github/jira/ai_analysis no-op 스텁)
    rds.py                Postgres 접속·조회 (psycopg 지연 import)
    sink_clickhouse.py    ClickHouse HTTP 적재 (stdlib urllib, JSONEachRow)
    sql/                  mock RDS 스키마+시드, ClickHouse DDL (compose init 마운트)
teams.json              이메일 → 팀 매핑 (저장소 루트)
```

전체 처리 진입점은 `src/processor.py`의 `process(doc)`다. 내부에서 `normalize(doc)`가 만든
`Normalized` 스트림에 `enrich(events)`를 적용해 `list[Enriched]`를 반환하고, 리시버가
이를 ClickHouse 에 배치 적재한다. 정규화기는 `call_id` 페어링을 위해 OTLP push 한 건을
내부 버퍼링하며, enrichment 도 같은 push 단위로 RDS 연결을 열고 닫는다.

새 외부 의존성(GitHub/Jira/AI 분석)은 `src/enrichment/providers/`에 파일 하나를
추가하는 것만으로 registry 에 자동 등록된다(코어 수정 0). provider 산출물은 공통 컬럼으로
승격하지 않고 `enrichment_json` 으로만 적재한다 — org 만 whitelist 컬럼을 채우는 예외.

```bash
python src/otlp_receiver.py
```

**Normalized{Log,Span,Metric}** = `model/event.py`의 신호별 스키마. 셋이 공통 **`Envelope`**
(`identity`/`client`/`session_id`/`timestamp`/`record_id`/`_ingest`)를 품고, 신호별 상관 필드와
payload만 각자 갖는다:
- `NormalizedLog` — `turn_id`/`call_id`/`sequence` + payload(`Prompt`/`LlmCall`/`LlmResponse`/`ToolCall`/`ToolDecision`/`Lifecycle`)
- `NormalizedSpan` — `trace_id`/`span_id`/`parent_id`/`call_id`/`span_role` + payload(타이밍만; 토큰·비용은 로그가 싣는다)
- `NormalizedMetric` — `MetricPoint`(name/value/unit/type/temporality/attrs)

조인은 병합이 아니라 **다운스트림 group-by**로: LLM은 `request_id`, 툴은 `call_id`, 그 위는 `session_id`.
신호 간 집계는 반드시 한 종류(`logs` 파일 등)만 세어 이중계산을 피한다.

지원 툴: **Claude Code**(`claude_code.*`), **Codex**(`codex.*`).
Codex adapter는 공식 문서 스키마 기준 **to-spec** — 토큰 키명 등은 실데이터로 재확인 필요.
확인 방법: 실데이터를 흘린 뒤 diagnostics의 `unmapped_fields` 집계를 확인한다.

### 이 모델에서 꼭 지켜야 할 3가지

1. **값이 없으면 0이 아니라 `None`.** "0건"과 "측정 불가"는 다른 사실이다.
   Codex는 커밋/PR/라인을 *측정할 수 없다* — 0으로 채우면 대시보드가 거짓말을 한다.
2. **토큰 합산은 `Tokens.billable`(input+output+cache_read+cache_create)로만.**
   `reasoning`(Codex reasoning_output, Gemini thoughts)과 `tool`(Gemini)은 `output`의
   부분집합일 수 있어 더하면 이중계산이다. `total_reported`는 검산 전용.
3. **`call_id`는 조인 키다.** Claude Code만 `tool_use_id`를 준다. Codex는 없어서
   어댑터가 합성하고(`call_id_synthesized=True`), `_pair_call_ids()`가 세션 내
   "같은 도구명의 직전 미결 승인"과 짝지어 tool_decision↔tool_call을 잇는다.
   수락률 KPI가 이 조인에 걸려 있다.

## 산출물

- **세부작업 분해**: 세션별 세그먼트 `[라벨, 토큰, cost, 턴, 소요, 대표 모듈/명령]`
  라벨: `구현/편집`·`탐색/조사`·`테스트`·`인프라/운영`·`문서`·`커밋/PR`·`서브에이전트`·`기타`
- **캐시 효율**: `cache_read/create/input`, hit-rate, 추정 절감액
- **source 분해**: main vs auxiliary(서브에이전트) 토큰 비중
- **롤업**: 개발자별 / 팀별 / 툴별
- **추세**: 지난 실행 대비 토큰·비용·개발자별 델타 (`history.jsonl`)

## 동작 원리

1. **정규화** — adapter가 툴 감지 후 원시 OTLP를 Normalized{Log,Span,Metric}로
2. **세그먼트 경계** — 유휴 갭 / 단계 마커(commit·test·build) / 모듈 전환
3. **"기타" 병합** — 도구 활동 없는 토큰-only 구간(사고·질문)은 인접 세부작업에 흡수
4. **귀속** — `llm_call` 토큰/비용을 해당 세그먼트에 합산 (`cost_usd` 없으면 pricing으로 추정)

## 한계 (설계상 감수)

- 토큰 귀속·세그먼트 경계는 휴리스틱 근사
- Codex 토큰 키명은 to-spec — 실데이터 연결 시 diagnostics의 미매핑 키 집계로 후보 확인
- `src/normalizer/pricing.py` 단가는 **자리표시자** — 실제 가격표로 갱신 필요 (캐시 절감액은 러프한 추정)
- 원문 미사용이라 "의도(why)"의 세밀한 라벨은 Phase 2(클라이언트 hook)에서
- **메트릭 매퍼 미완** — 리시버는 세 신호를 다 받지만 metrics 어댑터가 아직 스텁이라
  Claude Code의 라인/커밋/PR/active_time(메트릭에만 존재)이 `Artifact`로 안 들어온다.
  생산성 지표를 쓰려면 `src/normalizer/adapters/*/metrics.py`를 채워야 한다.
- **Codex는 `turn_id`가 없다** — 세그먼트 경계가 유휴 갭 휴리스틱에만 의존한다.
  CC/Gemini는 `prompt.id`/`prompt_id`로 턴 경계를 정확히 잡을 수 있다(아직 미활용).

## 검산

출력의 `검산 raw=... OK` = **세그먼트 토큰 합 == 세션 전체 `llm_call` 토큰 합** (귀속 누락 없음).
