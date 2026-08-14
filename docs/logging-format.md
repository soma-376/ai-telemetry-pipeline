# 로그 포맷 공유 스펙

> 파이프라인 서비스들이 CloudWatch 로 내보내는 **구조화 로그의 공통 계약**이다.
> **PROJ-51**(auth-proxy, TS)이 레퍼런스 구현이고 **PROJ-54**(telemetry-processor, Python)가 이를 따른다.
> **봉투(envelope)만 고정**하고, event 별 필드는 각 서비스가 확장한다.

## 1. 목적 · 범위

CloudWatch Logs Insights 에서 **여러 서비스 로그를 하나의 쿼리로** 조회·집계하기 위한 스펙이다.
서비스 구현 언어가 달라도(TS·Python) 봉투 4필드와 `outcome` 축이 동일해야 그룹을 가로지르는
쿼리가 성립한다. **봉투가 계약이고, 그 밖의 필드는 event 마다 자유다.**

이 스펙에 걸리는 것: 봉투 4필드, `level` 집합, `outcome` 값, 출력 규칙, event 이름.
걸리지 않는 것: event 별 도메인 필드(자유롭게 추가).

## 2. 출력 규칙

- **JSON Lines** — 이벤트 하나 = stdout 한 줄 = 유효한 JSON 객체 하나.
- **stdout/stderr 무관** — 로그 드라이버가 같은 스트림으로 캡처한다. 심각도는 스트림이 아니라
  `level` 필드로 구분한다. (error·warn 을 stderr 로 보내도 되지만 분류의 근거로 삼지 않는다.)
- `ts` 는 **UTC ISO-8601**(`2026-08-13T05:29:50.188Z`). 운영 로그에 로컬타임·pretty 포맷 금지.
- **비밀 금지** — 토큰 평문, `Authorization` 헤더, 프롬프트·응답 원문, payload 본문을 넣지 않는다.
  식별자(tokenId·tenantId 등 id)는 허용.
- **멀티라인은 필드 안에** — 스택 트레이스는 `stack` 필드에 escape 된 `\n` 문자열로 넣어 한 줄을
  유지한다. 생 멀티라인으로 찍으면 CloudWatch 가 프레임마다 별도 이벤트로 쪼갠다.
- **JSON 키는 camelCase** — 레퍼런스 구현(auth-proxy)이 그렇게 내보낸다. Python 변수는 snake_case
  라도 직렬화 시 camelCase 키로 매핑한다(키 이름이 서비스마다 갈리면 cross-query 가 깨진다).

## 3. 봉투 — 모든 로그에 공통

| 필드 | 타입 | 필수 | 의미 |
|---|---|---|---|
| `ts` | string | ✅ | UTC ISO-8601 (`…Z`) |
| `service` | string | ✅ | 서비스 식별자. `auth-proxy` · `telemetry-processor` |
| `level` | string | ✅ | 심각도. 4절 |
| `event` | string | ✅ | 이벤트 종류. snake_case. 판별자(discriminator) |
| `correlationId` | string | 선택 | 요청/메시지 상관 id (auth-proxy 의 `requestId`, processor 의 메시지 id) |

봉투 뒤에 event 별 필드가 이어진다: `{ ts, service, level, event, ...event별 필드 }`.

## 4. `level` — 심각도

집합: `error` · `warn` · `info` · `debug`. (`silent` 은 출력 안 함을 뜻하는 **설정값**이지 로그에
찍히는 값이 아니다.) 기준은 **"운영자가 조치해야 하나?"** 이다.

| level | 언제 | 예 |
|---|---|---|
| `error` | 서비스·파이프라인이 고장. 조치 필요 | 5xx, 업스트림 장애, uncaught 예외, DB 접근 불가 |
| `warn` | 클라이언트·데이터 문제지만 **서비스는 정상** | 4xx(401·400), 정규화 불가 레코드 |
| `info` | 정상 완료 · lifecycle | 2xx 요청, 서버 시작/종료, 집계 flush |
| `debug` | 상세 진단 | 요청 헤더, 내부 상태 |

**HTTP 4xx 는 `error` 가 아니다.** 클라이언트 오류(401 등)는 서비스가 제대로 동작한 것이므로
`warn`. 급증은 개별 로그가 아니라 집계·알림으로 잡는다.

노출 제어는 **단일 임계값 env `LOG_LEVEL`** 로 한다(`silent`→`error`→`warn`→`info`→`debug`).
설정한 레벨과 그보다 심각한 것이 전부 켜진다.

## 5. `outcome` — 데이터 유실 추적 축

`level` 과 **직교**한다. `level` 은 "서비스가 건강한가", `outcome` 은 **"데이터가 목적지에
도달했나"**. 데이터 유실은 레벨이 아니라 이 필드로 추적한다.

| 서비스 | `outcome` 값 | 유실? |
|---|---|---|
| auth-proxy | `delivered` | — |
| | `rejected` (인증·검증 실패로 전달 전 폐기) | 유실 |
| | `failed` (업스트림 장애로 전달 실패) | 유실 |
| telemetry-processor | `processed` | — |
| | `dropped` · `retried` · `dead_lettered` | 유실/지연 (실패 정책 확정 후 확정 — **열림**) |

- `outcome` 이 성공값(`delivered`/`processed`)이 아니면 유실 후보다.
- 구체 원인은 **`outcomeCause`**(예: `upstream_timeout`, `clickhouse_unreachable`) 또는 서비스별
  detail 필드(auth-proxy 의 `authReason`)에 담는다.
- 클라이언트에 주는 응답 코드/본문과 무관하게 로그의 `outcome` 이 유실의 단일 진실원이다.

> **처리 정책(drop / retry / DLQ)은 PROJ-54 에서 결정한다.** 권고 프레임: **transient(인프라
> 장애: ClickHouse·PG 다운·타임아웃) → 유계 재시도 → 소진 시 DLQ**, **permanent(정규화 불가·
> 스키마 위반: diagnostics 가 잡는 부류) → 재시도 무의미 → DLQ 또는 drop+진단 로그.** 어느 쪽이든
> 매 메시지의 처분을 위 `outcome` 으로 로깅한다.

## 6. event 카탈로그

### auth-proxy (PROJ-51, 구현됨)

| event | level | 필드 |
|---|---|---|
| `server_started` | info | `port`, `logLevel` |
| `server_stopping` | info | `signal` |
| `otlp_request` | status 로 결정 (2xx=info·4xx=warn·5xx=error) | `requestId`, `method`, `path`, `status`, `durationMs`, `product`, `auth{tokenId,tenantId,installationId,memberId}`, `outcome`, `outcomeCause?`, `authReason?`, `errorCode?`, `headers?`(debug) |
| `unhandled_error` | error | `message`, `stack` |

### telemetry-processor (PROJ-54, 목표)

| event | level | 필드 |
|---|---|---|
| `service_started` / `service_stopping` | info | lifecycle |
| `message_processed` | info | `correlationId`, `outcome:"processed"`, 도메인 필드 |
| `message_failed` | warn/error | `correlationId`, `outcome:"dropped\|retried\|dead_lettered"`, `outcomeCause` |
| `diagnostic_summary` | warn | `adapter`, `issue`, `reason`, `occurrenceCount`, `breakdownBy`, `breakdown?` (7절) |
| `unhandled_error` | error | `message`, `stack` (글로벌 예외 처리에서) |

새 event 는 자유롭게 추가하되 이름은 snake_case, 봉투를 지킨다.

## 7. diagnostics → 집계 flush

`src/diagnostics` 의 `AggregatingReporter` 는 **건별 로그가 아니라** 집계다(인메모리, 재시작 시
소실). 이를 CloudWatch 에 durable 하게 남기려면 **집계를 주기적으로 flush** 해 `diagnostic_summary`
로 emit 한다.

- **주기**(예 30~60s) + **종료 시 최종 flush**(마지막 창 유실 방지).
- **델타로 emit** — 직전 flush 이후 증가분만. CloudWatch 에서 `sum()` 하면 총량이 나온다.
  누적값을 매번 내보내면 중복 집계된다.
- group(`adapter`·`issue`·`reason`) 당 한 줄:

```json
{"ts":"…","service":"telemetry-processor","level":"warn","event":"diagnostic_summary",
 "adapter":"codex","issue":"mapping_miss","reason":"source_key_missing",
 "occurrenceCount":3,"breakdownBy":"target_field","breakdown":{"payload.model":3}}
```

`GET /diagnostics` snapshot 은 그대로 두고(실시간 조회용), 로그는 그 위에 durable 사본을 얹는 것이다.

## 8. CloudWatch 구조

3단 계층: **Log Group → Log Stream → Log Event(우리 JSON 한 줄)**.

- **Log Group = 서비스별 하나.** `/pulsemetry/auth-proxy`, `/pulsemetry/telemetry-processor`.
  서비스가 물리적으로 분리되므로 서로 섞이지 않는다. 보존기간·권한도 서비스별로 건다.
- **서비스 내 분류 = `event` 필드.** 진단(`diagnostic_summary`)과 운영(`otlp_request` 등)은 같은
  그룹, 쿼리 필터로 가른다.
- **통합 조회 = Insights 가 여러 그룹을 한 쿼리로** 훑는다. 봉투가 같아서 가능하고, `service`
  필드로 cross-group 그룹핑한다.

예시 쿼리:

```
# 파이프라인 전체 데이터 유실 (두 그룹 동시 선택)
filter outcome not in ["delivered","processed"] | stats count() by service, outcome, outcomeCause

# 인증 유실 원인 분해 (auth-proxy 그룹)
filter event="otlp_request" and outcome="rejected" | stats count() by authReason

# 스키마 드리프트 (processor 그룹)
filter event="diagnostic_summary" | stats sum(occurrenceCount) by adapter, issue, reason
```

## 9. 구현 메모

- **TS(auth-proxy)** — `apps/auth-proxy/src/shared/logging/logger.ts` 가 레퍼런스. `{ts, level,
  event, ...}` 를 `JSON.stringify` 로 stdout 에. 글로벌 예외는 Express error 미들웨어에서
  `unhandled_error`.
- **Python(telemetry-processor)** — `structlog` 또는 stdlib `logging` + `python-json-logger` 로
  동일 봉투 emit. 글로벌 예외 처리(미들웨어/최상위 핸들러)에서 auth-proxy 의 `unhandled_error` 와
  동등한 라인 emit.
- `service` 필드는 서비스마다 상수로 박거나 env(`SERVICE_NAME`)로 주입.

## 10. 변경 규칙

- **봉투 4필드 · `level` 집합 · `outcome` 값**은 **양 서비스 합의로만** 바꾼다. 한쪽이 바꾸면
  cross-group 쿼리가 조용히 깨진다.
- event 별 도메인 필드는 자유롭게 추가·변경 가능(다른 서비스에 영향 없음).
- 키 casing(camelCase)과 `ts` 포맷(UTC ISO)은 불변.
