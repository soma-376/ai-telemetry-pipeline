-- enrollment 스키마 — Pulsemetry 온보딩/신원/계약 모델(mock RDS).
-- compose 가 /docker-entrypoint-initdb.d 로 마운트해 최초 초기화 시 자동 적용(01-schema → 02-seed).
-- 볼륨이 없으므로 down 후 up 마다 재적용된다 → 결정론적 리셋
--   (dev compose 초기화의 기준 파일이라는 뜻이며, 스키마의 진실원이 아니다.
--    이 파일은 로컬 테스트·스키마 확인용 사본이다. enrollment 스키마 DDL 의 진실원은
--    pulsemetry-backend 의 Flyway 다 — backend ADR 0004·0009,
--    pulsemetry-backend/libs/enrollment-persistence/src/main/resources/db/migration/.
--    스키마를 바꿔야 하면 이 파일이 아니라 backend Flyway 를 고친다.)
-- 스키마를 통째로 DROP 후 재생성한다(enum 타입까지 깨끗이 리셋).
-- 이력(소급 변경 금지) 테이블은 기존 row 를 수정하지 않고 *_at 구간으로 시점 이력을 남긴다.

DROP SCHEMA IF EXISTS enrollment CASCADE;
CREATE SCHEMA enrollment;
SET search_path TO enrollment, public;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
CREATE TYPE tenant_status       AS ENUM ('active', 'suspended', 'terminated');
CREATE TYPE team_status         AS ENUM ('active', 'archived');
CREATE TYPE member_role         AS ENUM ('owner', 'admin', 'member');
CREATE TYPE member_status       AS ENUM ('invited', 'active', 'suspended');
CREATE TYPE installation_status AS ENUM ('active', 'revoked');
CREATE TYPE platform_type       AS ENUM ('windows', 'macos', 'linux');
CREATE TYPE ai_vendor           AS ENUM ('anthropic', 'openai', 'google');
CREATE TYPE contract_type       AS ENUM ('term_commitment', 'token_discount');
CREATE TYPE contract_status     AS ENUM ('draft', 'active', 'expired', 'terminated');
CREATE TYPE token_type          AS ENUM ('input', 'output', 'cache_read', 'cache_create', 'all');

-- ---------------------------------------------------------------------------
-- 조직 · 구성원
-- ---------------------------------------------------------------------------

-- Pulsemetry 를 사용하는 고객 조직.
CREATE TABLE tenants (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       varchar(100) NOT NULL,
    slug       varchar(100) UNIQUE,
    timezone   varchar(50)  NOT NULL DEFAULT 'Asia/Seoul',
    logo_url   text,
    status     tenant_status NOT NULL DEFAULT 'active',
    created_at timestamptz  NOT NULL DEFAULT now(),
    updated_at timestamptz  NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

-- 조직 구성원. 관리자 등 웹 사용자는 Cognito 계정과 연결되고,
-- 일반 사용자는 installation 을 통해 서비스와 연결된다(cognito_user_sub NULL 허용).
CREATE TABLE members (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES tenants(id),
    cognito_user_sub varchar(255),
    email            varchar(320) NOT NULL,
    display_name     varchar(100),
    role             member_role   NOT NULL DEFAULT 'member',
    status           member_status NOT NULL DEFAULT 'active',
    created_at       timestamptz   NOT NULL DEFAULT now(),
    updated_at       timestamptz   NOT NULL DEFAULT now(),
    -- NULL 은 서로 distinct 취급 → CLI 전용(cognito_user_sub NULL) 다수 공존 가능.
    UNIQUE (tenant_id, cognito_user_sub),
    UNIQUE (tenant_id, email)
);
CREATE INDEX ON members (cognito_user_sub);

-- tenant 내부에서 구성원/AI 사용량을 구분하는 팀 또는 부서 단위.
CREATE TABLE teams (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  uuid NOT NULL REFERENCES tenants(id),
    name       varchar(100) NOT NULL,
    status     team_status  NOT NULL DEFAULT 'active',
    created_at timestamptz  NOT NULL DEFAULT now(),
    updated_at timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);
CREATE INDEX ON teams (tenant_id);

-- 구성원의 팀 소속 관계와 소속 기간. left_at NULL = 현재 소속(as-of 조인 키).
CREATE TABLE team_memberships (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id   uuid NOT NULL REFERENCES teams(id),
    member_id uuid NOT NULL REFERENCES members(id),
    joined_at timestamptz NOT NULL DEFAULT now(),
    left_at   timestamptz
);
CREATE INDEX ON team_memberships (team_id);
CREATE INDEX ON team_memberships (member_id);

-- ---------------------------------------------------------------------------
-- 온보딩 · 설치 · 자격증명
-- ---------------------------------------------------------------------------

-- CLI 설치를 허용하는 일회성 초대 코드. 설치(enrollment)에 한 번만 사용된다.
CREATE TABLE invitations (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL REFERENCES tenants(id),
    target_member_id     uuid NOT NULL REFERENCES members(id),
    created_by_member_id uuid NOT NULL REFERENCES members(id),
    code_hash            varchar(255) NOT NULL UNIQUE,
    used_at              timestamptz,
    expires_at           timestamptz NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    revoked_at           timestamptz
);
CREATE INDEX ON invitations (tenant_id);
CREATE INDEX ON invitations (expires_at);

-- 사용자 PC 에 설치된 Pulsemetry CLI/daemon.
CREATE TABLE installations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      uuid NOT NULL REFERENCES tenants(id),
    member_id      uuid NOT NULL REFERENCES members(id),
    invitation_id  uuid NOT NULL REFERENCES invitations(id),
    hostname       varchar(255),
    platform       platform_type NOT NULL,
    architecture   varchar(30),
    client_version varchar(50),
    status         installation_status NOT NULL DEFAULT 'active',
    last_seen_at   timestamptz,
    revoked_at     timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON installations (member_id);
CREATE INDEX ON installations (invitation_id);
CREATE INDEX ON installations (tenant_id, status);

-- installation 의 장기 신원 자격증명(telemetry token 발급 근거).
-- 원본은 로컬 기기에만, 서버에는 해시만.
CREATE TABLE installation_credentials (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id uuid NOT NULL REFERENCES installations(id),
    credential_hash varchar(255) NOT NULL UNIQUE,
    issued_at       timestamptz NOT NULL DEFAULT now(),
    last_used_at    timestamptz,
    revoked_at      timestamptz
);
CREATE INDEX ON installation_credentials (installation_id);
CREATE INDEX ON installation_credentials (installation_id, revoked_at);

-- installation_credentials 를 근거로 발급되는 인증 토큰(OTLP 헤더에 실려오는 값).
-- installation 과 1:N — 재발급/만료/폐기 이력을 관리. 프록시는 이 테이블을 검증한다.
CREATE TABLE telemetry_tokens (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id uuid NOT NULL REFERENCES installations(id),
    token_hash      varchar(255) NOT NULL UNIQUE,
    issued_at       timestamptz NOT NULL DEFAULT now(),
    last_used_at    timestamptz,
    revoked_at      timestamptz
);
CREATE INDEX ON telemetry_tokens (installation_id);
CREATE INDEX ON telemetry_tokens (installation_id, revoked_at);
-- backend Flyway V3 동기화 — installation 당 활성 토큰은 최대 하나 (재발급 계약의 최종 방어선).
CREATE UNIQUE INDEX ux_telemetry_tokens_installation_active
    ON telemetry_tokens (installation_id)
    WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- 수집/privacy 정책 (manifest)
-- ---------------------------------------------------------------------------

-- tenant 별 수집·privacy 정책의 버전 이력. 변경 시 새 version 을 생성(기존 row 불변).
CREATE TABLE manifests (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL REFERENCES tenants(id),
    version              int   NOT NULL,
    manifest             jsonb NOT NULL,
    is_active            boolean NOT NULL DEFAULT false,
    created_by_member_id uuid NOT NULL REFERENCES members(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    activated_at         timestamptz,
    UNIQUE (tenant_id, version)
);
CREATE INDEX ON manifests (tenant_id, is_active);
-- backend Flyway V2 동기화 — tenant 당 활성 manifest 는 최대 하나 (dbml 에 없는 의도적 추가, SCHEMA-DRIFT).
CREATE UNIQUE INDEX ux_manifests_tenant_active
    ON manifests (tenant_id)
    WHERE is_active;

-- installation 에 배포된 manifest 버전과 적용 여부.
CREATE TABLE installation_manifest_assignments (
    installation_id uuid NOT NULL REFERENCES installations(id),
    manifest_id     uuid NOT NULL REFERENCES manifests(id),
    assigned_at     timestamptz NOT NULL DEFAULT now(),
    applied_at      timestamptz,
    PRIMARY KEY (installation_id, manifest_id)
);
CREATE INDEX ON installation_manifest_assignments (manifest_id);

-- ---------------------------------------------------------------------------
-- 계약 (AI 벤더)
-- ---------------------------------------------------------------------------

-- tenant 가 AI 벤더와 체결한 계약. 벤더별·기간별 다수 가능.
-- ends_at NULL = 종료일 미정. contract_type 에 따라 상세 테이블을 가진다.
CREATE TABLE contracts (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL REFERENCES tenants(id),
    vendor               ai_vendor     NOT NULL,
    contract_type        contract_type NOT NULL,
    name                 varchar(100)  NOT NULL,
    contract_no          varchar(100),
    contracted_at        date NOT NULL,
    starts_at            date NOT NULL,
    ends_at              date,
    status               contract_status NOT NULL DEFAULT 'active',
    created_by_member_id uuid REFERENCES members(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    terminated_at        timestamptz,
    UNIQUE (tenant_id, contract_no)
);
CREATE INDEX ON contracts (tenant_id);
CREATE INDEX ON contracts (tenant_id, vendor);
CREATE INDEX ON contracts (tenant_id, status);
CREATE INDEX ON contracts (starts_at, ends_at);

-- term_commitment 계약 상세(contracts 와 1:1 — PK 가 곧 FK).
CREATE TABLE contract_term_commitments (
    contract_id       uuid PRIMARY KEY REFERENCES contracts(id),
    commitment_months int NOT NULL,
    commitment_amount numeric(18,4),
    currency          char(3) NOT NULL DEFAULT 'USD',
    auto_renew        boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- token_discount 계약 상세이자 환산용 메타. discount_rate 는 정가에 곱하는 배율
-- (0.80000 = 20% 할인). 도중 변경 시 기존 row 불변 + effective_from/to 로 시점 이력.
-- model_pattern NULL = 해당 벤더의 모든 모델에 적용.
CREATE TABLE contract_token_discounts (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id    uuid NOT NULL REFERENCES contracts(id),
    model_pattern  varchar(100),
    token_type     token_type NOT NULL DEFAULT 'all',
    discount_rate  numeric(6,5) NOT NULL,
    effective_from date NOT NULL,
    effective_to   date,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (contract_id, model_pattern, token_type, effective_from)
);
CREATE INDEX ON contract_token_discounts (contract_id);
CREATE INDEX ON contract_token_discounts (contract_id, effective_from);

-- member 가 어떤 계약의 적용을 받는지에 대한 배정과 기간. released_at NULL = 현재 유효.
CREATE TABLE contract_memberships (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id uuid NOT NULL REFERENCES contracts(id),
    member_id   uuid NOT NULL REFERENCES members(id),
    assigned_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz
);
CREATE INDEX ON contract_memberships (contract_id);
CREATE INDEX ON contract_memberships (member_id);
