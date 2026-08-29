# Diagnostics

```text
apps/telemetry-processor/diagnostics/
├─ __init__.py                 # 외부에 공개하는 진단 클래스와 타입
├─ engine.py                   # 이슈 탐지, reason 판별, 필터링
├─ model.py                    # Observation, Issue, Finding, DiagnosticEvent
├─ tracking.py                 # 소스 키 접근과 대상 필드 매핑 시도 추적
├─ reporter.py                 # DiagnosticReporter 계약과 NullReporter
├─ aggregating_reporter.py     # 진단 이벤트의 인메모리 집계와 snapshot
└─ snapshot_cli.py             # 실행 중인 집계를 타임스탬프 JSON으로 저장

(테스트 스위트는 PROJ-40 에서 삭제됨 — 복원 과제는 docs/production-readiness.md P1-8)
```

## 목적

Diagnostics는 벤더 텔레메트리의 스키마 변화와 정규화 누락을 탐지한다.
원본 이벤트를 건별로 기록하는 로거가 아니라, 문제 유형과 대상의 발생 횟수를
집계하는 진단 모듈이다.

- 정규화되지 않은 제품 이벤트 탐지
- 대상 필드 매핑 실패 탐지
- 정규화 결과의 불변 조건 위반 탐지
- 어댑터가 읽지 않은 소스 키 탐지
- 동일 문제를 adapter, issue, reason 단위로 집계

## 처리 흐름

```text
OTLP record
    ↓
Adapter
    ↓
TrackingAttrs
    ↓
Observation
    ↓
Diagnostics
    ↓
DiagnosticEvent
    ↓
AggregatingReporter
    ↓
snapshot
```

제품 namespace 밖의 레코드는 Adapter 매칭 단계에서 제외되며 Diagnostics로
전달되지 않는다.

## 이슈 종류

| issue               | 의미                                                       | 대표 reason                                                    |
| ------------------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| `unknown_event`     | 스키마로 정규화 불가                                       | `normalization_not_supported`                                  |
| `mapping_miss`      | 어댑터가 매핑을 시도한 정규화 대상 필드의 결과가 Null이 됨 | `source_key_missing`, `source_value_null`, `conversion_failed` |
| `invariant_failure` | 정규화된 값이 스키마 규칙을 위반함(int로 했는데 str이던가) | `invalid_timestamp`, `token_total_mismatch`, `unknown_session` |
| `unmapped_fields`   | 소스에 있지만 어댑터가 읽지 않은 키                        | `source_key_not_read`                                          |

## 범위 판별

```text
어떤 Adapter namespace에도 매칭되지 않음
    ↓
out-of-scope
    ↓
진단하지 않음
```

```text
Adapter namespace에 매칭됨
    ↓
to_event()가 None 반환
    ↓
unknown_event
    ↓
후속 mapping, invariant, unmapped 검사 중단
```

```text
Adapter namespace에 매칭됨
    ↓
to_event()가 Normalized 반환
    ↓
mapping, invariant, unmapped 검사 수행
```

## TrackingAttrs

`TrackingAttrs`는 어댑터가 사용하는 일반 `dict`를 감싸며 다음 접근을 자동으로
기록한다.

- `attrs.get(key)`
- `attrs[key]`
- `key in attrs`

`attrs.map()`은 하나의 대상 필드를 만드는 동안 접근한 소스 키와 변환 결과를
기록한다.

```python
model = attrs.map(
    "payload.model",
    lambda: _opt_str(attrs, keys=("model",)),
)
```

### 매핑 결과 정책

- 필수 필드의 소스 키가 없음 → `source_key_missing`
- 소스 키는 있지만 값이 모두 `None` → `source_value_null`
- 값은 있지만 변환 결과가 `None` → `conversion_failed`
- `required=False`이고 소스 키도 없음 → 진단하지 않음
- `required=False`라도 키가 존재하고 변환에 실패함 → 진단

현재 target field 단위의 mapping 추적은 Codex logs 위주로 적용되어 있다.

## Invariant 정책

- timestamp가 숫자가 아니거나 0 이하 → `invalid_timestamp`
- session 매핑은 성공했지만 값이 `"(unknown)"` → `unknown_session`
- session mapping miss가 이미 있으면 `unknown_session` 중복 진단 억제
- token `reconciles()`가 `False` → `token_total_mismatch`
- token `reconciles()`가 `None` → 검산 불가이므로 진단하지 않음
- event type이 `other`이거나 필수 payload가 없음 → `unsupported_event_payload`
- decision이 `unknown` → `unknown_decision`
- span ID 또는 trace ID가 없음 → 각각 누락 invariant
- metric point의 이름이 없음 → `missing_metric_name`

현재 decision 소스가 누락되어 `mapping_miss`가 발생하고 최종 decision도
`unknown`이면 두 이슈를 모두 기록한다.

## 집계

`AggregatingReporter`는 다음 키로 동일한 진단 이벤트를 그룹화한다.

```text
adapter
    ↓
issue
    ↓
reason
    ↓
breakdown_by
```

예시:

```json
[
  {
    "adapter": "codex",
    "issue": "mapping_miss",
    "reason": "source_key_missing",
    "occurrence_count": 3,
    "breakdown_by": "target_field",
    "breakdown": {
      "payload.model": 3
    }
  }
]
```

`occurrence_count`는 해당 그룹의 진단 이벤트 발생 횟수다. `unmapped_fields`는
한 원본 이벤트에서 여러 키를 포함할 수 있으므로 breakdown 합계가
`occurrence_count`보다 클 수 있다.

동일 원본 이벤트 안에 같은 breakdown 항목이 중복되어도 한 번만 센다.

## Snapshot

실행 중인 processor의 현재 집계는 다음 endpoint에서 확인한다.

```text
GET http://localhost:8080/diagnostics
```

타임스탬프 JSON 파일로 저장:

```powershell
python src\diagnostics\snapshot_cli.py
```

기본 출력 위치:

```text
data/diagnostics/diagnostics-summary-YYYYMMDD-HHMMSS-KST.json
```

snapshot은 현재 집계를 초기화하지 않는다. 현재 집계는 인메모리 상태이므로
processor가 재시작되면 초기화된다.

## 개인정보와 원본 데이터

- 정규화 스키마의 `_ingest.raw`와 `raw_value`는 사용하지 않는다.
- prompt와 response 원문을 snapshot이나 집계 결과에 저장하지 않는다.
- diagnostics 출력에는 문제 유형, 대상 필드, 소스 키 이름, count만 남긴다.
- 원본 OTLP 데이터 보존은 diagnostics가 아닌 원본 아카이브 파이프라인의 책임이다.

## 새 매핑 추가 절차

1. 해당 Adapter에서 대상 필드의 `attrs.map()` 적용 여부를 결정한다.
2. target field 이름을 정규화 스키마 경로로 지정한다.
3. 필수 여부에 따라 `required` 값을 지정한다.
4. 성공, 키 누락, null, 변환 실패 테스트를 추가한다.
5. 실제 데이터를 흘린 뒤 snapshot의 mapping miss와 unmapped key를 확인한다.

## 테스트

전체 diagnostics 테스트 실행:

```powershell
$env:PYTHONPATH='src'
python -B -m unittest discover -s tests -t . -v
```

현재 테스트는 다음 정책을 검증한다.

- unknown event gatekeeper
- mapping miss reason
- session 중복 억제
- token 검산의 `True`, `False`, `None` 계약
- invariant 판별
- 미매핑 키 계산
- 인메모리 집계와 thread safety
- snapshot 조회와 안전한 파일 저장

## 향후 확장

DB 저장이 필요해지면 집계와 flush 책임을 분리한다.

```text
AggregatingReporter
    ↓
원자적 drain
    ↓
FlushWorker
    ↓
DatabaseSink
```

`AggregatingReporter`는 집계만 담당하고, 주기 실행·재시도·DB 연결은 별도
구성요소가 담당한다.
