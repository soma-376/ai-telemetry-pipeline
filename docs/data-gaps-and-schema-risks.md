# 데이터 누락 · 스키마 취약점 정리

전체 소스(`src/`, collector 설정, compose)를 훑은 결과. 심각도 순.

## 1. 치명적 — 데이터가 실제로 사라지는 경로

### 1.1 정규화 결과가 어디에도 저장되지 않는다
`otlp_receiver.py:43` — `for _event in process(...): pass`. enrichment까지 계산한 뒤 전부 버린다.
원본 아카이브(`data/{codex,claude_code}/*.jsonl`)만 남고, 정규화 스트림은 휘발.
README에 명시된 한계지만
사실상 파이프라인의 최종 산출물이 0건이다.

### 1.2 배치 내 레코드 1건만 깨져도 배치 전체가 영구 유실된다
`otlp_receiver.py:45` — 예외 시 무조건 **400** 반환. OTLP 스펙상 4xx는 재시도 불가(permanent)
오류라 collector가 해당 배치를 그대로 버린다. JSON 파싱 오류·어댑터 버그 하나가
같은 push에 실린 정상 레코드 수백 건을 같이 지운다. (일시 장애면 5xx, 레코드 단위 오류면
격리 후 200이 맞다.)

### 1.3 collector 재시도 큐가 메모리 큐다
`otel-collector-config.yaml` — `otlphttp` exporter에 `sending_queue.storage`(file_storage) 미설정.
"리시버가 잠깐 죽어도 큐가 흡수한다"(README)는 collector 프로세스가 살아있을 때만 참이고,
collector 재시작 시 큐에 있던 데이터는 유실. 큐가 가득 차도 drop.

### 1.4 tool_decision ↔ tool_call 페어링이 한 push 안에서만 동작
`normalize.py:79` — `pair_call_ids(events)`가 **OTLP push 한 건** 범위로만 실행된다.
collector의 `batch` processor가 승인(decision)과 실행(call)을 다른 배치로 쪼개면
조인이 조용히 끊긴다. 승인 대기(사용자가 몇 초 고민)가 배치 타임아웃보다 길면 거의 항상 분리됨.
→ **수락률 KPI 과소집계**. 세션 단위 상태 저장 없이는 구조적으로 못 잇는다.

## 2. 높음 — 조용히 오염되는 데이터

### 2.1 타임스탬프 파싱 실패 시 0.0 (1970-01-01)
`otlp/timestamp.py:21` — 파싱 실패가 진단 없이 epoch 0으로 떨어진다. record_id 해시,
시간순 페어링 정렬, 세그먼트 경계가 전부 timestamp에 걸려 있어 한 건이 전체 세션 정렬을
망가뜨린다. 진단 이벤트도 안 남는다.

### 2.2 session_id 폴백 `"(unknown)"`으로 전 사용자 병합
`claude_code/logs.py:108`, `codex/logs.py:93` — 세션 ID가 없으면 모두 같은 `"(unknown)"`
버킷으로 합쳐진다. `pair_call_ids`가 세션 단위로 돌기 때문에 **서로 다른 사용자의
decision/call이 교차 페어링**될 수 있다.

### 2.3 매칭 안 된 어댑터 내부 이벤트가 진단 없이 빈 레코드가 된다
어댑터 `match()`는 prefix만 보므로, `claude_code.*`/`codex.*`인데 분기에 없는 이벤트명은
`LogKind.OTHER` + `payload=None`으로 방출된다. `unknown_event` 진단은 어댑터가 아예 매칭
안 됐을 때만 발화(`normalize.py:68`) → 새 이벤트 타입이 추가돼도 아무도 모른다.
(예: Codex의 신규 이벤트, CC의 `session_start` 등.)

### 2.4 record_id 충돌 → 중복 제거 시 과소집계
`envelope.py:129` — sequence가 없고(코덱스에서 흔함) 같은 ts·같은 내용이면 두 레코드가
한 record_id로 합쳐진다. 코드 주석으로 인지된 위험이지만, 코덱스 OTHER 이벤트
(discriminator `"-"`)는 특히 충돌 확률이 높다.

### 2.5 pending 승인 덮어쓰기
`call_id.py:54` — 같은 도구명의 승인이 연달아 두 번 오면 `pending[key] = ...`가 앞선 미결
승인을 덮어써 그 decision은 영영 페어링되지 않는다.

### 2.6 `_opt_int`가 음수·부호 있는 문자열을 버린다
`otlp/attributes.py:34` — `"‑5"` 같은 문자열은 `isdigit()` 실패로 None. 음수 delta 메트릭이나
오류 코드가 문자열로 오면 누락된다.

## 3. 중간 — 스키마/보안 취약점

| # | 위치 | 문제 |
|---|------|------|
| 3.1 | `otel-collector-config.yaml` | **metrics 파이프라인에 redaction 미적용** — 시크릿이 metric attr로 오면 그대로 `point.attrs`에 저장 |
| 3.2 | `otlp/raw.py:35` | 원문 denylist가 `prompt`/`response` 두 키뿐 — `content`, `message`, `tool_output` 등은 raw로 통과. `command`(full_command)에 섞인 시크릿은 collector 정규식에만 의존 |
| 3.3 | `normalize.py:57` | `tenant.id`를 클라이언트가 보낸 resource 속성에서 읽는다 — `context.py`는 "신뢰 가능한 출처"라 주장하지만 실제론 **클라이언트 주장값**. 인증 기반 스탬핑 없음 |
| 3.4 | `otlp_receiver.py:35-38` | Content-Length·gzip 해제 크기 무제한(압축 폭탄), 인증·TLS 없음, `0.0.0.0` 바인드 |
| 3.5 | `common/metric.py` | `summary` 타입 미처리, `exponentialHistogram`의 positive/negative 버킷 구조 미추출(빈 리스트로 저장) |
| 3.6 | `docker-compose.dev.yml` | collector 이미지 `latest` — 재현 불가, 파일 exporter 무한 append(로테이션 없음) |
| 3.7 | README ↔ 코드 드리프트 | README의 `--idle-gap`/`--teams`/`--history` 옵션, `teams.json`, 세그먼트 분해·롤업 기능이 **레포에 존재하지 않음**. `model/SCHEMA.md`는 삭제된 상태 |

## 4. 알려진(의도된) 공백 — 참고

- Codex 매핑은 to-spec, 실데이터 미검증 (토큰 키명 등 diagnostics 집계로 확인 필요)
- metrics 어댑터는 통과만 시킴 — CC의 라인/커밋/PR/active_time이 `Artifact`로 승격 안 됨
  (`LogKind.ARTIFACT`·`Artifact` payload는 정의만 있고 생산자가 없음)
- Codex traces 어댑터 스텁 (`codex/traces.py`)
- `pricing.py` 단가는 자리표시자
- Codex `turn_id` 부재 → 세그먼트는 유휴 갭 휴리스틱 의존
