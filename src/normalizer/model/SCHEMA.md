# 정규화 스키마 (Normalized Schema)

CLI AI 툴(Claude Code / Codex …)의 OTLP 텔레메트리를 정규화한 내부 데이터 모델.
`normalizer/model/` 의 dataclass 가 곧 wire(JSON) 모양이다 (`asdict` 직렬화).

## 개요

정규화 결과는 **신호(signal)별 3개 타입**이며, 셋은 공통 **`Envelope`** 를 품는다.

```
Envelope (공유: 누가·무엇으로·언제·어느 세션)
├─ NormalizedLog     점(event)   — 무슨 일이 일어났다
├─ NormalizedSpan    구간(interval) — 시작~끝이 있는 실행 구간 (트리)
└─ NormalizedMetric  측정값       — 집계 카운터/게이지/히스토그램
```

- **파일 배치**: `common.py`(봉투+공유 payload) · `log.py` · `span.py` · `metric.py` · `types.py`(union) · `enums.py`
- **출력**: `Normalized` 스트림을 enrichment 단계에 그대로 전달한다.
- **조인**: 병합하지 않는다. 다운스트림이 `session_id`(세션) / `request_id`(LLM) / `call_id`(툴) 로 group-by.

---

## 최상위 타입

### `NormalizedLog` — 로그 이벤트 (점)

| 필드 | 타입 | 설명 |
|---|---|---|
| `envelope` | `Envelope` | 공통 봉투 (아래) |
| `type` | `LogKind` | 이벤트 종류 |
| `payload` | `LogPayload` | 종류별 페이로드 (`Prompt`/`LlmCall`/`LlmResponse`/`ToolCall`/`ToolDecision`/`Lifecycle`/`null`) |
| `turn_id` | `str?` | 턴 상관 ID. CC=`prompt.id`, Codex=없음 |
| `call_id` | `str?` | 툴 조인 키. `tool_decision ↔ tool_result` 를 잇는다 |
| `sequence` | `int?` | 세션 내 단조 카운터 (CC=`event.sequence`). 정렬·멱등키 재료 |

### `NormalizedSpan` — 스팬 (구간)

| 필드 | 타입 | 설명 |
|---|---|---|
| `envelope` | `Envelope` | 공통 봉투 |
| `type` | `SpanKind` | 스팬 역할 (=OTel span 이름) |
| `payload` | `SpanPayload` | `LlmCall`/`ToolCall`/`ToolDecision`/`Lifecycle`/`null`. **토큰·비용은 안 담는다**(로그와 이중계산 회피) |
| `trace_id` | `str?` | 트리 전체를 묶는 ID |
| `span_id` | `str?` | 이 노드 |
| `parent_id` | `str?` | 부모 노드로의 간선. 트리 조립은 뷰가 이걸로 |
| `call_id` | `str?` | 툴 조인 키 (`tool_use_id`) |

### `NormalizedMetric` — 메트릭 datapoint

| 필드 | 타입 | 설명 |
|---|---|---|
| `envelope` | `Envelope` | 공통 봉투 |
| `point` | `MetricPoint` | 측정값 (아래). 조인은 세션/actor/시간 단위(거친 granularity) |

### `Normalized`

```python
Normalized = Union[NormalizedLog, NormalizedSpan, NormalizedMetric]
```

---

## 공통 (Envelope)

### `Envelope`

세 신호가 공유. 신호별 상관 키(turn_id·span_id 등)는 여기 없다 — 각 타입이 자기 것만 갖는다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `identity` | `Identity` | 누가 |
| `client` | `Client` | 어떤 제품으로 |
| `timestamp` | `float` | epoch seconds |
| `session_id` | `str` | 신호 간 조인의 최상위 키 |
| `schema_version` | `int` | 스키마 버전 |
| `record_id` | `str` | 결정적 멱등키. `finalize` 가 원시 값에서 계산 (재읽기해도 동일) |
| `_ingest` | `Ingest` | 수집·정규화 배관 (KPI 는 안 읽음) |

### `Identity` — 누가

정본 신원은 `user_id` (온보딩 때 회사가 박은 값, 벤더 무관). 벤더 값은 정보성.

| 필드 | 타입 | 설명 |
|---|---|---|
| `tenant_id` | `str?` | 회사 식별자 (테넌트/조직 파티션) |
| `user_id` | `str?` | 정본 사용자 식별자. `None` = 온보딩 누락 → 미귀속 |
| `vendor_email` | `str?` | 벤더가 준 이메일. 정본 아님 (개인계정 감지용) |
| `vendor_account_id` | `str?` | 벤더가 준 계정 ID. 정본 아님 (빌링 대조용) |

> team/role/organization 은 여기 없다 — enrichment 가 `user_id` 로 조인해 매핑한다.

### `Client` — 무엇으로

| 필드 | 타입 | 설명 |
|---|---|---|
| `product` | `str` | `claude_code` \| `codex` \| `gemini_cli` … (열린 집합) |
| `surface` | `Surface` | 실행 환경 |
| `version` | `str?` | 앱 버전 |

### `Ingest` — 어떻게 수집했나 (배관)

wire 키는 `_ingest`. KPI 는 읽지 않는다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `adapter_version` | `int` | 이 레코드를 파싱한 어댑터 버전 (마이그레이션·provenance) |
| `signal` | `SignalType` | `log` \| `span` \| `metric` |
| `source_record_id` | `str?` | 원본 레코드로의 back-pointer (payload_hash) |
| `call_id_inferred` | `bool` | 어댑터가 call_id 를 합성했나 (Codex) |
| `raw_value` | `str?` | 정규화하며 죽는 원값 보존 (예: 원본 decision 문자열) |
| `raw` | `dict[str,str]` | 미매핑 속성 = 다음 승격 후보 |

---

## 페이로드 (Payload)

### `Prompt` — 사용자 프롬프트 *(log 전용)*

| 필드 | 타입 | 설명 |
|---|---|---|
| `length` | `int?` | 프롬프트 길이 (문자). 본문은 담지 않는다 |
| `command_name` | `str?` | 슬래시 명령 이름 |

### `LlmCall` — LLM 호출 *(log·span 공유)*

로그(`api_request`)·스팬(`llm_request`) 둘 다 이걸 쓴다. 스팬에선 `tokens`/`cost_usd`/`source` 를 **안 채운다**(이중계산 회피).

| 필드 | 타입 | 설명 |
|---|---|---|
| `model` | `str?` | 모델 식별자 |
| `tokens` | `Tokens` | 토큰 (로그만) |
| `cost_usd` | `float?` | 비용 USD (CC 만 직접 제공) |
| `cost_source` | `ValueSource` | `reported` \| `estimated` |
| `source` | `str?` | 요청 발급 하위 시스템 (CC=`query_source`) |
| `duration_ms` | `int?` | 소요 시간 |
| `ttft_ms` | `int?` | 첫 토큰까지 시간 |
| `stop_reason` | `str?` | `end_turn`/`tool_use`/`max_tokens`/`refusal`… |
| `attempt` | `int?` | 총 시도 횟수 |
| `request_id` | `str?` | Anthropic 요청 ID. **로그↔스팬 LLM 조인 키** |
| `error_type` | `str?` | 오류 종류 |
| `status_code` | `int?` | 실패 시 HTTP 상태 코드 |

### `Tokens` — 토큰

| 필드 | 타입 | 설명 |
|---|---|---|
| `input` / `output` / `cache_read` / `cache_create` | `int?` | **청구 기준.** 이 4개만 합산 (`billable`) |
| `reasoning` | `int?` | Codex reasoning / Gemini thoughts. `output` 부분집합 가능 → **합산 금지** |
| `tool` | `int?` | Gemini tool tokens. **합산 금지** |
| `total_reported` | `int?` | 툴이 준 총계. 검산 전용 (`reconciles()`) |

- `billable` (property): `input+output+cache_read+cache_create`
- `reconciles()`: `total_reported == billable` 인지 (`None` = 총계 미제공)

### `LlmResponse` — LLM 응답측 *(log 전용)*

`api_request` 와 짝(응답). 토큰은 `LlmCall` 에 있고 여기엔 응답 고유 정보만. `request_id` 로 조인.

| 필드 | 타입 | 설명 |
|---|---|---|
| `model` | `str?` | 모델 |
| `response_length` | `int?` | 응답 길이 |
| `source` | `str?` | query_source |
| `request_id` | `str?` | `api_request` 와 조인 |
| `stop_reason` | `str?` | 정지 사유 |
| `refusal_category` | `str?` | 거부 카테고리 (api_refusal) |

### `ToolCall` — 툴 호출 *(log·span 공유)*

| 필드 | 타입 | 설명 |
|---|---|---|
| `tool_name` | `str?` | 도구 이름 |
| `tool_kind` | `ToolKind` | native \| mcp \| skill … |
| `action` | `ToolAction` | read \| edit \| exec … |
| `files` | `list[str]` | 대상 파일 경로 |
| `command` | `str?` | 실행 명령 |
| `success` | `bool?` | 성공 여부 |
| `error_type` | `str?` | 오류 종류 |
| `duration_ms` | `int?` | 소요 시간 |
| `mcp_server` | `str?` | MCP 서버 이름 |
| `agent_id` / `parent_agent_id` | `str?` | 서브에이전트 식별 |

### `ToolDecision` — 승인 결정 *(log·span 공유)*

| 필드 | 타입 | 설명 |
|---|---|---|
| `decision` | `Decision` | accept \| modify \| reject \| abort |
| `decided_by` | `DecisionSource` | user \| config \| hook … |
| `scope` | `DecisionScope` | once \| session \| permanent … |
| `blocked_on_user_ms` | `int?` | 승인 대기 시간 (스팬) |
| `tool_name` | `str?` | 대상 도구 (조인 없이 집계하려 비정규화) |

### `Lifecycle` — 세션·수명주기 *(log·span 공유)*

| 필드 | 타입 | 설명 |
|---|---|---|
| `kind` | `str` | `session_start` \| `compaction` \| `turn` \| `hook` … |
| `start_type` | `str?` | 시작 유형 |
| `active_time_sec` | `int?` | 활성 시간 |
| `turn_count` | `int?` | 턴 수 |
| `tokens_before` / `tokens_after` | `int?` | 압축 전후 컨텍스트 크기 (**청구 토큰 아님**) |
| `attrs` | `dict[str,str]` | 승격 안 한 부가 속성 |

### `Artifact` — 산출물 *(log 전용)*

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | `str` | `commit` \| `pull_request` \| `code_lines` … |
| `action` | `str` | 기본 `created` |
| `id` | `str?` | 산출물 ID |
| `value` | `float?` | 수치 |
| `unit` | `str?` | 단위 |
| `attrs` | `dict[str,str]` | 부가 속성 |

### `MetricPoint` — 메트릭 datapoint *(metric 전용)*

OTLP 메트릭 datapoint 를 충실히 미러링.

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | `str` | 메트릭 이름 |
| `value` | `int\|float?` | 값 (number datapoint). 히스토그램이면 `null` |
| `unit` | `str?` | 단위 |
| `description` | `str?` | 설명 |
| `metric_type` | `str?` | `sum` \| `gauge` \| `histogram` … |
| `aggregation_temporality` | `int?` | 1=delta, 2=cumulative (OTLP 원값) |
| `is_monotonic` | `bool?` | 단조 증가 여부 (sum) |
| `start_time` | `float?` | datapoint 시작 시각 (윈도우 시작; 끝은 envelope.timestamp) |
| `count` / `sum` / `min` / `max` | `int?`/`float?` | 히스토그램 집계 |
| `bucket_counts` | `list[int]` | 히스토그램 버킷 카운트 |
| `explicit_bounds` | `list[float]` | 히스토그램 경계 |
| `attrs` | `dict[str,str]` | datapoint 속성 (type/model/decision 등 — 여기 핵심 정보) |

---

## Enum

| Enum | 값 |
|---|---|
| `SignalType` | `log` `metric` `span` |
| `Surface` | `unknown` `cli` `ide` `web_ext` `api` `ci` |
| `ValueSource` | `reported` `estimated` |
| `LogKind` | `user_prompt` `artifact` `lifecycle` `llm_call` `llm_response` `tool_call` `tool_decision` `other` |
| `SpanKind` | `turn` `llm_request` `tool` `tool_gate` `tool_execution` `hook` `other` |
| `ToolKind` | `unknown` `native` `mcp` `skill` `subagent` `extension` `api` `custom` |
| `ToolAction` | `other` `read` `search` `write` `edit` `delete` `exec` `fetch` `generate` |
| `Decision` | `unknown` `accept` `modify` `reject` `abort` |
| `DecisionSource` | `unknown` `user` `config` `hook` `policy` `system` |
| `DecisionScope` | `unknown` `once` `session` `project` `workspace` `permanent` |

### `SpanKind` ↔ CC 스팬 매핑

| `SpanKind` | OTel 스팬 |
|---|---|
| `turn` | `claude_code.interaction` |
| `llm_request` | `claude_code.llm_request` |
| `tool` | `claude_code.tool` (권한대기+실행 전체 구간) |
| `tool_gate` | `claude_code.tool.blocked_on_user` |
| `tool_execution` | `claude_code.tool.execution` |
| `hook` | `claude_code.hook` (베타·게이트) |

---

## 조인 키 요약

| 레벨 | 키 | 어디에 |
|---|---|---|
| LLM 호출 | `request_id` | `LlmCall`/`LlmResponse.request_id` (payload) |
| 툴 호출 | `call_id` | `NormalizedLog/Span.call_id` (context) |
| 스팬 트리 | `parent_id` → `span_id` | `NormalizedSpan` |
| 세션 | `session_id` | `Envelope` |
| 사용자 | `user_id` | `Envelope.identity` |

> **이중계산 주의**: 같은 툴/LLM 호출이 로그와 스팬 양쪽에서 나온다. 집계는 한 신호(`signal`)만 세라. 토큰·비용은 로그(`api_request`)가 정본, 스팬은 타이밍만.
