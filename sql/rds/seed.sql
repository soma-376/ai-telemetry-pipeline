-- enrollment 결정론적 시드. 고정 UUID/해시로 재현 가능한 상태를 만든다.
-- 의도적 엣지 케이스:
--   * telemetry_tokens: 유효 1 + 회전(폐기) 1 + 폐기된 설치의 토큰 1 → 프록시 검증 분기 커버.
--   * installations: active 2 + revoked 1(설치 자체 폐기).
--   * team_memberships: Bob 이 backend → platform 으로 이동(as-of 이력, 겹침·공백 없음).
--   * invitations: 사용된 것 + 미사용(Dave, 초대만 하고 미설치).
--   * members: active + invited(Dave).
--
-- 해시 컬럼(*_hash)은 프록시 해시 스킴에 맞춰 계산한 값이다.
--   telemetry_tokens.token_hash = HMAC-SHA256(TOKEN_HASH_SECRET, raw_token) 의 hex.
--   (프록시: shared/crypto/token-hash.ts, 시드 기준 secret = 'local-development-secret-change-me')
-- 각 토큰 줄의 raw_token 원본은 주석으로 보존한다(재계산/클라이언트 설정용).
-- 그 외 자격증명/초대 해시는 아직 가독 placeholder 다.

SET search_path TO enrollment, public;

-- ---- tenants ----
INSERT INTO tenants (id, name, slug, timezone, status) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Acme Corp',  'acme',   'Asia/Seoul', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'Globex Inc', 'globex', 'UTC',        'active');

-- ---- members ----
INSERT INTO members (id, tenant_id, cognito_user_sub, email, display_name, role, status) VALUES
  -- Acme
  ('a0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'cog-alice', 'alice@acme.test', 'Alice', 'owner',  'active'),
  ('a0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', NULL,        'bob@acme.test',   'Bob',   'member', 'active'),
  -- Dave: 초대만 받고 아직 설치 안 함(invited).
  ('a0000004-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', NULL,        'dave@acme.test',  'Dave',  'member', 'invited'),
  -- Globex
  ('a0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'cog-carol', 'carol@globex.test', 'Carol', 'admin', 'active');

-- ---- teams ----
INSERT INTO teams (id, tenant_id, name, status) VALUES
  ('b0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Platform', 'active'),
  ('b0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Backend',  'active'),
  ('b0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'Data',     'active');

-- ---- team_memberships (as-of 이력) ----
-- Alice: platform 상시. Bob: backend[.., 2026-06-01) → platform[2026-06-01, NULL) 인접.
INSERT INTO team_memberships (id, team_id, member_id, joined_at, left_at) VALUES
  ('c1000001-0000-0000-0000-000000000001', 'b0000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', TIMESTAMPTZ '2020-01-01T00:00:00Z', NULL),
  ('c1000002-0000-0000-0000-000000000002', 'b0000002-0000-0000-0000-000000000002', 'a0000002-0000-0000-0000-000000000002', TIMESTAMPTZ '2020-01-01T00:00:00Z', TIMESTAMPTZ '2026-06-01T00:00:00Z'),
  ('c1000003-0000-0000-0000-000000000003', 'b0000001-0000-0000-0000-000000000001', 'a0000002-0000-0000-0000-000000000002', TIMESTAMPTZ '2026-06-01T00:00:00Z', NULL),
  ('c1000004-0000-0000-0000-000000000004', 'b0000003-0000-0000-0000-000000000003', 'a0000003-0000-0000-0000-000000000003', TIMESTAMPTZ '2020-01-01T00:00:00Z', NULL);

-- ---- invitations ----
-- 생성자는 Alice(owner). 설치에 사용된 것 3 + Dave 미사용(pending) 1.
INSERT INTO invitations (id, tenant_id, target_member_id, created_by_member_id, code_hash, used_at, expires_at, revoked_at) VALUES
  ('d0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a0000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', 'invite-hash-alice',     TIMESTAMPTZ '2026-01-10T00:00:00Z', TIMESTAMPTZ '2026-12-31T00:00:00Z', NULL),
  ('d0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a0000002-0000-0000-0000-000000000002', 'a0000001-0000-0000-0000-000000000001', 'invite-hash-bob',       TIMESTAMPTZ '2026-01-11T00:00:00Z', TIMESTAMPTZ '2026-12-31T00:00:00Z', NULL),
  ('d0000003-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a0000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', 'invite-hash-alice-2',   TIMESTAMPTZ '2026-02-01T00:00:00Z', TIMESTAMPTZ '2026-12-31T00:00:00Z', NULL),
  -- Dave: 미사용(used_at NULL) — 초대만 하고 설치는 아직.
  ('d0000004-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'a0000004-0000-0000-0000-000000000004', 'a0000001-0000-0000-0000-000000000001', 'invite-hash-dave',      NULL,                               TIMESTAMPTZ '2026-12-31T00:00:00Z', NULL);

-- ---- e2e 초대 (실사용 가능) ----
-- code_hash = HMAC-SHA256('dev-only-invite-pepper', 'E2E-INVITE-0001')  (config.invitePepper 기본값)
-- 미사용·미폐기·미만료 → `pulsemetry enroll --invite E2E-INVITE-0001 --server <enroll-server>` 로 1회 소모.
-- 대상 tenant=Acme(활성 manifest 보유). enroll 이 installation·credential·telemetry_token 을 생성한다.
INSERT INTO invitations (id, tenant_id, target_member_id, created_by_member_id, code_hash, used_at, expires_at, revoked_at) VALUES
  ('d00000e2-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a0000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', 'd284b584f34683aa78b46e9ddaf19cca97f726046d73d36f3ff3d8288af5ec67', NULL, TIMESTAMPTZ '2027-12-31T00:00:00Z', NULL);

-- ---- installations ----
-- inst-alice, inst-bob: active. inst-alice-old: 폐기된 두 번째 기기(revoked).
INSERT INTO installations (id, tenant_id, member_id, invitation_id, hostname, platform, architecture, client_version, status, last_seen_at, revoked_at) VALUES
  ('e0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'a0000001-0000-0000-0000-000000000001', 'd0000001-0000-0000-0000-000000000001', 'alice-mbp',  'macos',   'arm64', '0.4.0', 'active',  TIMESTAMPTZ '2026-08-06T09:00:00Z', NULL),
  ('e0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'a0000002-0000-0000-0000-000000000002', 'd0000002-0000-0000-0000-000000000002', 'bob-desktop','windows', 'x86_64','0.4.0', 'active',  TIMESTAMPTZ '2026-08-06T08:30:00Z', NULL),
  ('e0000003-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'a0000001-0000-0000-0000-000000000001', 'd0000003-0000-0000-0000-000000000003', 'alice-old',  'linux',   'x86_64','0.3.0', 'revoked', TIMESTAMPTZ '2026-05-01T00:00:00Z', TIMESTAMPTZ '2026-05-02T00:00:00Z');

-- ---- installation_credentials (장기 신원) ----
INSERT INTO installation_credentials (id, installation_id, credential_hash, revoked_at) VALUES
  ('f1000001-0000-0000-0000-000000000001', 'e0000001-0000-0000-0000-000000000001', 'cred-hash-alice', NULL),
  ('f1000002-0000-0000-0000-000000000002', 'e0000002-0000-0000-0000-000000000002', 'cred-hash-bob',   NULL),
  -- 폐기된 설치의 자격증명도 폐기.
  ('f1000003-0000-0000-0000-000000000003', 'e0000003-0000-0000-0000-000000000003', 'cred-hash-alice-old', TIMESTAMPTZ '2026-05-02T00:00:00Z');

-- ---- telemetry_tokens (프록시가 검증하는 값) ----
-- 검증 쿼리:
--   SELECT i.tenant_id, i.member_id
--   FROM telemetry_tokens t JOIN installations i ON i.id = t.installation_id
--   WHERE t.token_hash = $1 AND t.revoked_at IS NULL
--     AND i.status = 'active' AND i.revoked_at IS NULL;
INSERT INTO telemetry_tokens (id, installation_id, token_hash, issued_at, revoked_at) VALUES
  -- 유효: Alice 현재 토큰.  raw_token=06ab85c6d1396d4cc4de6b3415ebed7aa23f3b02ac696fd290dcc0c358a90668
  ('f2000001-0000-0000-0000-000000000001', 'e0000001-0000-0000-0000-000000000001', 'e8238d483da112fc4107648b7644848adf9d48e57bfd99c33f02ead2f8f410e6', TIMESTAMPTZ '2026-07-01T00:00:00Z', NULL),
  -- 회전 이력: Alice 의 이전 토큰(폐기됨) → 검증 시 거부되어야 함.  raw_token=51ced987fd2d66cae55ca54a8b28ca48ef6a31e301e29f5533d0aad7b488718e
  ('f2000002-0000-0000-0000-000000000002', 'e0000001-0000-0000-0000-000000000001', '52deec029c8148d9733fac7446512d30f5d3ada033c82a940a6efc39edc2bf6b', TIMESTAMPTZ '2026-01-15T00:00:00Z', TIMESTAMPTZ '2026-07-01T00:00:00Z'),
  -- 유효: Bob 현재 토큰.  raw_token=8df3dd970d91116dee7a4dcb50c11326da49a94468e06aeb2fc629729674e7f5
  ('f2000003-0000-0000-0000-000000000003', 'e0000002-0000-0000-0000-000000000002', '8a4de3c9618bde0ee6ca4fd7831850e4c2e2c490e31a904b6479a200c450141d', TIMESTAMPTZ '2026-07-01T00:00:00Z', NULL),
  -- 토큰 자체는 미폐기지만 설치가 revoked → 검증 시 거부되어야 함(설치 상태로 컷).  raw_token=d8a3630f2059762c7652dd575668ce110c399eb57dae90aa042929fa99e4407d
  ('f2000004-0000-0000-0000-000000000004', 'e0000003-0000-0000-0000-000000000003', 'e4377bc8db721f3c69ec47e693cf549346f079db46279f832bc474a25e253103', TIMESTAMPTZ '2026-04-01T00:00:00Z', NULL);

-- ---- manifests + 배포 ----
INSERT INTO manifests (id, tenant_id, version, manifest, is_active, created_by_member_id, activated_at) VALUES
  ('aa000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 1,
   '{"schema_version": 1, "config_revision": 1, "otlp": {"endpoint": "http://localhost:4316", "protocol": "http/protobuf"}, "signals": {"logs": true, "metrics": true, "traces": true}, "privacy": {"collect_user_prompts": false, "collect_assistant_responses": false, "collect_tool_details": false, "collect_tool_content": false, "collect_user_email": false, "collect_raw_api_bodies": false}, "repository_allowlist": [], "resource_attributes": {"deployment.environment": "e2e"}}'::jsonb,
   true, 'a0000001-0000-0000-0000-000000000001', TIMESTAMPTZ '2026-01-10T00:00:00Z');

INSERT INTO installation_manifest_assignments (installation_id, manifest_id, applied_at) VALUES
  ('e0000001-0000-0000-0000-000000000001', 'aa000001-0000-0000-0000-000000000001', TIMESTAMPTZ '2026-01-10T01:00:00Z'),
  ('e0000002-0000-0000-0000-000000000002', 'aa000001-0000-0000-0000-000000000001', TIMESTAMPTZ '2026-01-11T01:00:00Z');

-- ---- contracts ----
-- 1) 기간 약정(anthropic).  2) 토큰 할인(openai).
INSERT INTO contracts (id, tenant_id, vendor, contract_type, name, contract_no, contracted_at, starts_at, ends_at, status, created_by_member_id) VALUES
  ('bb000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'anthropic', 'term_commitment', 'Acme × Anthropic 2026', 'ACME-ANT-2026', DATE '2025-12-15', DATE '2026-01-01', DATE '2026-12-31', 'active', 'a0000001-0000-0000-0000-000000000001'),
  ('bb000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'openai',    'token_discount',  'Acme × OpenAI 2026',    'ACME-OAI-2026', DATE '2025-12-20', DATE '2026-01-01', NULL,             'active', 'a0000001-0000-0000-0000-000000000001');

INSERT INTO contract_term_commitments (contract_id, commitment_months, commitment_amount, currency, auto_renew) VALUES
  ('bb000001-0000-0000-0000-000000000001', 12, 120000.0000, 'USD', true);

-- 배율 이력: 상반기 20% 할인(0.80000) → 하반기 25% 할인(0.75000)으로 변경(기존 row 불변).
INSERT INTO contract_token_discounts (id, contract_id, model_pattern, token_type, discount_rate, effective_from, effective_to) VALUES
  ('cc000001-0000-0000-0000-000000000001', 'bb000002-0000-0000-0000-000000000002', NULL, 'all', 0.80000, DATE '2026-01-01', DATE '2026-07-01'),
  ('cc000002-0000-0000-0000-000000000002', 'bb000002-0000-0000-0000-000000000002', NULL, 'all', 0.75000, DATE '2026-07-01', NULL);

-- ---- contract_memberships ----
INSERT INTO contract_memberships (id, contract_id, member_id, released_at) VALUES
  ('dd000001-0000-0000-0000-000000000001', 'bb000001-0000-0000-0000-000000000001', 'a0000001-0000-0000-0000-000000000001', NULL),
  ('dd000002-0000-0000-0000-000000000002', 'bb000001-0000-0000-0000-000000000001', 'a0000002-0000-0000-0000-000000000002', NULL);
