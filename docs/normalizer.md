# Normalizer → Enrichment 데이터 명세

## 목적

Normalizer는 Codex와 Claude Code의 OTLP 데이터를 공통 스키마로 변환한다.  
`processor.process()`는 정규화에 성공한 이벤트만 `enrichment.enrich()`에 전달한다.

현재 enrichment는 이벤트를 수정하지 않는 pass-through 단계이므로, enrichment가 받는 데이터 타입은 아래와 같다.

```python
Normalized = NormalizedLog | NormalizedSpan | NormalizedMetric
```

OTLP 레코드가 어떤 어댑터에도 속하지 않거나, 어댑터가 이벤트를 정규화하지 못하면 diagnostics 검사 대상은 될 수 있지만 enrichment에는 전달되지 않는다.

## 처리 흐름

```text
OTLP document
      ↓
read_all()
      ↓
Codex / Claude Code Adapter
      ↓
NormalizedLog | NormalizedSpan | NormalizedMetric
      ↓
call_id 연결
      ↓
Enrichment
```

## 공통 Envelope

세 종류의 정규화 이벤트는 모두 `envelope`을 가진다.

```json
{
  "envelope": {
    "identity": {
      "tenant_id": "string | null",
      "member_id": "string | null",
      "vendor_email": "string | null",
      "vendor_account_id": "string | null"
    },
    "client": {
      "product": "codex | claude_code",
      "surface": "unknown | cli | ide | web_ext | api | ci",
      "version": "string | null"
    },
    "timestamp": 0.0,
    "session_id": "string",
    "schema_version": 1,
    "record_id": "idem-...",
    "_ingest": {
      "adapter_version": 1,
      "signal": "log | span | metric",
      "source_record_id": "raw-...",
      "call_id_inferred": false
    }
  }
}
```

### Envelope 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `identity.tenant_id` | `string \| null` | 리소스의 `tenant.id` |
| `identity.member_id` | `string \| null` | 파이프라인에서 사용하는 정규화 사용자 식별자 (현재는 클라이언트 자칭 폴백 — 허브 telemetry-ingest §5 M2) |
| `identity.vendor_email` | `string \| null` | 벤더가 제공한 이메일 |
| `identity.vendor_account_id` | `string \| null` | 벤더가 제공한 계정 식별자 |
| `client.product` | `string` | 현재 `codex` 또는 `claude_code` |
| `client.surface` | `Surface` | 현재 두 어댑터 모두 기본값 `cli` |
| `client.version` | `string \| null` | 애플리케이션 또는 서비스 버전 |
| `timestamp` | `float` | Unix timestamp(초) |
| `session_id` | `string` | 세션 식별자. 찾지 못하면 현재 `"(unknown)"` |
| `schema_version` | `int` | 정규화 스키마 버전. 현재 `1` |
| `record_id` | `string` | 정규화된 주요 필드로 만든 멱등 식별자 |
| `_ingest.adapter_version` | `int` | 이벤트를 만든 어댑터 버전 |
| `_ingest.signal` | `SignalType` | 원본 OTLP 신호 종류 |
| `_ingest.source_record_id` | `string \| null` | 원본 레코드에서 만든 추적용 해시 |
| `_ingest.call_id_inferred` | `bool` | 원본 call ID가 없어 합성했는지 여부 |

`_ingest`는 원본 payload를 보관하지 않으며, 수집 경로 추적에 필요한 메타데이터만 포함한다.

## NormalizedLog

```json
{
  "envelope": {},
  "type": "user_prompt | lifecycle | llm_call | llm_response | tool_call | tool_decision | other",
  "payload": {},
  "turn_id": "string | null",
  "call_id": "string | null",
  "sequence": "int | null"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | `LogKind` | 정규화된 로그 이벤트 종류 |
| `payload` | 로그 payload 또는 `null` | `type`에 대응하는 의미 데이터 |
| `turn_id` | `string \| null` | 대화 턴 식별자 |
| `call_id` | `string \| null` | 도구 호출과 결과 등을 연결하는 식별자 |
| `sequence` | `int \| null` | 세션 내부 이벤트 순서 |

### 로그 type과 payload

| `type` | payload |
|---|---|
| `user_prompt` | `Prompt` |
| `llm_call` | `LlmCall` |
| `llm_response` | `LlmResponse` |
| `tool_call` | `ToolCall` |
| `tool_decision` | `ToolDecision` |
| `lifecycle` | `Lifecycle` |
| `other` | 구체적인 payload를 만들지 못했을 때 사용하는 fallback 값 |

## NormalizedSpan

```json
{
  "envelope": {},
  "type": "turn | llm_request | tool | tool_gate | tool_execution | hook | other",
  "payload": {},
  "trace_id": "string | null",
  "span_id": "string | null",
  "parent_id": "string | null",
  "call_id": "string | null"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `type` | `SpanKind` | 정규화된 구간의 역할 |
| `payload` | span payload 또는 `null` | 역할에 대응하는 의미 데이터 |
| `trace_id` | `string \| null` | OTLP trace ID |
| `span_id` | `string \| null` | OTLP span ID |
| `parent_id` | `string \| null` | 부모 span ID |
| `call_id` | `string \| null` | 관련 도구 호출 식별자 |

### span type과 payload

| `type` | 의미 | payload |
|---|---|---|
| `turn` | 사용자 상호작용 구간 | `Lifecycle` |
| `llm_request` | LLM 요청 구간 | `LlmCall` |
| `tool` | 도구 호출 전체 구간 | `ToolCall` |
| `tool_gate` | 사용자 승인 대기 구간 | `ToolDecision` |
| `tool_execution` | 도구 실행 구간 | `ToolCall` |
| `hook` | hook 실행 구간 | `Lifecycle` |
| `other` | 알 수 없는 역할 | `null` 가능 |

현재 Claude Code span만 정규화한다. Codex trace 어댑터는 아직 구현되지 않아 Codex span은 enrichment에 전달되지 않는다.

## NormalizedMetric

```json
{
  "envelope": {},
  "point": {
    "name": "string",
    "value": "int | float | null",
    "unit": "string | null",
    "description": "string | null",
    "metric_type": "string | null",
    "aggregation_temporality": "int | null",
    "is_monotonic": "bool | null",
    "start_time": "float | null",
    "count": "int | null",
    "sum": "float | null",
    "min": "float | null",
    "max": "float | null",
    "bucket_counts": ["int"],
    "explicit_bounds": ["float"],
    "attrs": {
      "attribute.name": "string"
    }
  }
}
```

metric은 Codex와 Claude Code 모두 동일한 `MetricPoint` 구조로 전달한다. `value`는 단일 number point에 사용하고, `count`, `sum`, `min`, `max`, `bucket_counts`, `explicit_bounds`는 집계형 metric에 따라 선택적으로 채워진다.

`attrs`의 값은 enrichment 입력에서 모두 문자열로 변환된다. 원본 값이 객체나 배열이면 compact JSON 문자열로 저장된다.

## Payload 스키마

### Prompt

```json
{
  "length": "int | null",
  "command_name": "string | null"
}
```

프롬프트 본문은 포함하지 않으며 길이와 명령 이름만 전달한다.

### Tokens

```json
{
  "input": "int | null",
  "output": "int | null",
  "cache_read": "int | null",
  "cache_create": "int | null",
  "reasoning": "int | null",
  "tool": "int | null",
  "total_reported": "int | null"
}
```

`billable`과 `reconciles()`는 계산용 속성/메서드이므로 직렬화 필드에는 포함되지 않는다.

### LlmCall

```json
{
  "model": "string | null",
  "tokens": {},
  "cost_usd": "float | null",
  "cost_source": "reported | estimated",
  "source": "string | null",
  "reasoning_effort": "string | null",
  "duration_ms": "int | null",
  "ttft_ms": "int | null",
  "stop_reason": "string | null",
  "attempt": "int | null",
  "request_id": "string | null",
  "error_type": "string | null",
  "status_code": "int | null"
}
```

### LlmResponse

```json
{
  "model": "string | null",
  "response_length": "int | null",
  "source": "string | null",
  "request_id": "string | null",
  "stop_reason": "string | null",
  "refusal_category": "string | null"
}
```

응답 본문은 포함하지 않는다.

### ToolCall

```json
{
  "tool_name": "string | null",
  "tool_kind": "unknown | native | mcp | skill | subagent | extension | api | custom",
  "action": "other | read | search | write | edit | delete | exec | fetch | generate",
  "files": ["string"],
  "command": "string | null",
  "success": "bool | null",
  "error_type": "string | null",
  "duration_ms": "int | null",
  "mcp_server": "string | null",
  "agent_id": "string | null",
  "parent_agent_id": "string | null"
}
```

### ToolDecision

```json
{
  "decision": "unknown | accept | modify | reject | abort",
  "decided_by": "unknown | user | config | hook | policy | system",
  "scope": "unknown | once | session | project | workspace | permanent",
  "blocked_on_user_ms": "int | null",
  "tool_name": "string | null"
}
```

### Lifecycle

```json
{
  "kind": "string",
  "start_type": "string | null",
  "active_time_sec": "int | null",
  "turn_count": "int | null",
  "tokens_before": "int | null",
  "tokens_after": "int | null",
  "attrs": {
    "attribute.name": "string"
  }
}
```

`kind`에 따라 나머지 필드가 선택적으로 사용된다. 현재 예로 `session_start`, `mcp_connection`, `compaction`, `turn`, `hook`이 있다.

## 현재 지원 이벤트

### Codex

| OTLP signal | 원본 이벤트 | 정규화 결과 |
|---|---|---|
| log | `codex.sse_event` | token 정보가 있으면 `llm_call`, 없으면 `other` |
| log | `codex.tool_result` | `tool_call` |
| log | `codex.tool_decision` | `tool_decision` |
| log | `codex.user_prompt` | `user_prompt` |
| log | `codex.conversation_starts` | `lifecycle(session_start)` |
| metric | `codex.*` metric | `NormalizedMetric` |
| span | `codex.conversation_starts` | `turn` + `lifecycle(session_start)` |
| span | `codex.api_request` | `llm_request` |
| span | `codex.tool_result` | `tool_execution` |
| span | `codex.tool_decision` | `tool_gate` |
| span | 그 밖의 `codex.*` span | 전달하지 않는다 (어댑터가 `None` 반환) |

`codex.sse_event`에 token 정보가 없으면 현재 `type=other`, `payload=null`인
`NormalizedLog`로 enrichment에 전달된다. diagnostics는 이를
`unsupported_event_payload`로 진단하지만 전달 자체를 차단하지는 않는다.

### Claude Code

| OTLP signal | 원본 이벤트 | 정규화 결과 |
|---|---|---|
| log | `claude_code.api_request` | `llm_call` |
| log | `claude_code.assistant_response` | `llm_response` |
| log | `claude_code.api_error` | `llm_call` |
| log | `claude_code.api_refusal` | `llm_response` |
| log | `claude_code.tool_result` | `tool_call` |
| log | `claude_code.tool_decision` | `tool_decision` |
| log | `claude_code.mcp_server_connection` | `lifecycle(mcp_connection)` |
| log | `claude_code.compaction` | `lifecycle(compaction)` |
| log | `claude_code.user_prompt` | `user_prompt` |
| span | `claude_code.interaction` | `turn` |
| span | `claude_code.llm_request` | `llm_request` |
| span | `claude_code.tool` | `tool` |
| span | `claude_code.tool.execution` | `tool_execution` |
| span | `claude_code.tool.blocked_on_user` | `tool_gate` |
| span | `claude_code.hook` | `hook` |
| metric | `claude_code.*` metric | `NormalizedMetric` |

## 전달 규칙

1. 하나의 OTLP 문서는 0개 이상의 `Normalized` 이벤트를 만든다.
2. 지원 제품 namespace 밖의 레코드는 enrichment에 전달하지 않는다.
3. 지원 제품 namespace 안에서도 어댑터가 `None`을 반환한 이벤트는 전달하지 않는다.
4. 정규화 객체가 생성된 뒤 발견된 diagnostics 이슈는 현재 enrichment 전달을 차단하지 않는다.
5. 로그와 span의 관련 이벤트는 enrichment 전달 전에 가능한 범위에서 `call_id`로 연결한다.
6. 선택 필드는 원본 데이터가 없거나 변환할 수 없으면 `null` 또는 빈 배열로 남을 수 있다.
7. JSON 직렬화 시 enum은 위 표에 표시된 문자열 값으로 표현된다.

## 코드 기준 위치

```text
apps/telemetry-processor/normalizer/
├─ normalize.py               # 어댑터 선택, diagnostics 검사, call_id 연결, 이벤트 방출
├─ model/
│  ├─ common.py               # Envelope와 공통 payload
│  ├─ log.py                  # NormalizedLog와 로그 payload
│  ├─ span.py                 # NormalizedSpan
│  ├─ metric.py               # NormalizedMetric와 MetricPoint
│  ├─ enums.py                # type과 상태 enum
│  └─ types.py                # Normalized union
├─ adapters/
│  ├─ codex/                  # Codex → 공통 스키마
│  └─ claude_code/            # Claude Code → 공통 스키마
├─ common/
│  ├─ envelope.py             # 공통 envelope와 record_id 생성
│  ├─ metric.py               # 공통 metric 변환
│  ├─ context.py              # 수집 컨텍스트(IngestContext)
│  ├─ call_id.py              # call_id 합성과 페어링
│  └─ serialization.py        # JSON 직렬화 규칙
├─ otlp/                      # OTLP 파싱 공용 유틸. readers.py = 3 시그널 리더
└─ pricing.py                 # 토큰 기반 비용 추정 (단가는 자리표시자)

apps/telemetry-processor/enrichment/enrich.py   # Normalized 스트림에 조직 정보를 결합해 Enriched 로 만든다
apps/telemetry-processor/processor.py           # normalize 와 enrichment 연결
```
