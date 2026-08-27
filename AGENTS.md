# AGENTS.md — ai-telemetry-pipeline

Pulsemetry는 Claude Code·Codex 등 개발 AI 도구의 사용량과 비용을 조직 → 팀 → 구성원 축으로 모아 보여주는
사내 통합·가시화 플랫폼이다.

- 제품·아키텍처·레포 간 계약의 **단일 출처는 `soma-376/docs`**다. 형제 체크아웃 `../docs`를 우선 참조한다.
- 기능 작업 전에는 `spec` 스킬, 설계 관련 작업 전에는 `adr` 스킬을 쓴다.
- **코드와 ADR이 어긋나면 ADR이 기준이다.** 결정을 바꾸려면 `adr-new`로 개정 ADR을 먼저 쓴다.
- git 작업은 `CONVENTION.md`를 따른다 (`conventions` 스킬).
- 스킬이 보이지 않으면 형제 `../agent-skills` 클론 여부를 확인하고, 없으면 사용자에게 클론을 안내한다.
- 문서·주석은 한국어, 코드·파일명은 영어.
- **사용자의 명시 요청 없이 `git push` 하지 않는다.**

---

## 이 레포는 무엇인가

**앱 2개가 한 레포에 있다.** 시스템 아키텍처의 Collector 뒤편 — Masker·Adapter·Enricher 자리다.

```text
apps/auth-proxy/            TypeScript. OTLP 요청의 토큰 검증 → x-pulsemetry-* 4헤더 부여 → Authorization 제거
apps/telemetry-processor/   Python. 신원 스탬핑 → 벤더별 어댑터 정규화 → 조직 결합 → ClickHouse 적재
  normalizer/               claude_code. · codex. 이벤트 매핑
  enrichment/               team_memberships as-of 조인
otel-collector-config.yaml  ★ dev(in-repo) collector 설정 — 배포 설정은 infra 소유
sql/rds/                    dev 부트스트랩 DDL·시드 — 진실원이 아니다
```

**소유하는 것**: 토큰 검증과 신원 헤더 부여, OTLP 정규화 규칙, ClickHouse `enriched_events` 적재.

**소유하지 않는 것**
- **토큰 발급** → `pulsemetry-backend`
- **enrollment 스키마 DDL의 진실원** → `pulsemetry-backend`의 Flyway. `sql/rds/schema.sql`은 dev 편의용이다
- **배포 collector 설정** → `infra/config/otel-collector.yaml`. ECS가 실제로 기동하는 건 그쪽이다

## ⚠️ 문서 상태

README와 `docs/` 4종의 **코드 경로·구조 서술은 PROJ-79에서 `apps/` 배치에 맞췄다.**
README가 소개하던 "세부작업 분류 + 토큰 귀속 분석기" CLI는 이 레포에 없어서 걷어냈고,
데이터 흐름에 빠져 있던 auth-proxy를 넣었다. Codex traces 어댑터를 스텁이라 적은 서술 3곳도 고쳤다.

아직 코드와 대조하지 않은 것은 `docs/normalizer.md`·`docs/diagnostics.md`의 **필드 단위 정의**다.
경로·지원 이벤트 표·어댑터 등록은 확인했지만 payload 필드 하나하나까지는 보지 않았다.
**필드를 신뢰해야 하는 작업이면 코드를 먼저 본다.**

## 명령어

```bash
docker compose -f docker-compose.dev.yml up -d
cd apps/auth-proxy && npm ci && npm run typecheck && npm run build   # CI가 하는 것도 이것뿐
cd apps/telemetry-processor && pip install -r requirements.txt
```

**레포 테스트가 0개다.** CI는 auth-proxy typecheck/build만 돈다. 변경 시 수동 검증이 필요하다.

## 이 레포에서 특히 조심할 것

- **토큰 해시는 HMAC-SHA256(`TOKEN_HASH_SECRET`)이다.** backend가 같은 키·같은 연산으로 발급하므로
  **한쪽만 고치는 PR을 열지 않는다** (`../docs/contracts/enrollment-api.md` §4).
- **신원 전파 3요소**(`include_metadata` · `headers_setter` · `batch.metadata_keys`)는
  이 레포의 dev 설정과 **`infra/config/otel-collector.yaml` 양쪽에 있다** — PROJ-77(infra #6)로 맞췄다.
  한쪽만 고쳐 다시 어긋나면 ClickHouse의 `tenant_id`·`installation_id`가 빈 문자열이 된다.
  **collector 설정을 고칠 때는 두 파일을 함께 본다.**
- **`sql/rds/schema.sql`을 고쳐서 스키마를 바꾸지 않는다.** backend Flyway를 고친다.
  시드의 초대 코드 pepper(`dev-only-invite-pepper`)도 backend의 무염 SHA-256과 어긋나 있다.
- `enrollment` 스키마에 **쓰지 않는다.** 읽기 전용 소비자다.
- 알려진 결함은 `../docs/contracts/telemetry-ingest.md` §5에 모여 있다 (B3·M2~M6·M11·M12).
  **B4(배포 collector 설정 드리프트)는 PROJ-77로 해소됐다. 문서 쪽 표는 아직 갱신 전이다.**
- `docs/adr/`에 템플릿(`0000-adr-template.md`)만 있고 ADR은 아직 없다. 첫 번호는 `0001`,
  파일명은 영문 슬러그다 — `adr-new` 스킬이 안내한다.
