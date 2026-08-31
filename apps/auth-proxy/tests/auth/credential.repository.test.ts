import { beforeEach, describe, expect, it, vi } from "vitest";

// postgres.ts 는 import 시점에 new Pool() 을 만든다 — 실제 커넥션이 생기지 않도록
// 모듈째 스텁한다.
const { query } = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock("../../src/database/postgres.js", () => ({
  postgres: { query },
  closePostgres: vi.fn(),
}));

import { resolveTelemetryTokenByHash } from "../../src/auth/credential.repository.js";

interface TokenRow {
  token_id: string;
  token_revoked_at: Date | null;
  tenant_id: string;
  installation_id: string;
  member_id: string;
  installation_status: string;
  installation_revoked_at: Date | null;
  member_status: string;
  tenant_status: string;
  tenant_deleted_at: Date | null;
}

const REVOKED_AT = new Date("2026-01-01T00:00:00Z");

/** 모든 검사를 통과하는 정상 행. 케이스마다 한 필드씩만 무너뜨린다. */
function row(overrides: Partial<TokenRow> = {}): TokenRow {
  return {
    token_id: "tok-0001",
    token_revoked_at: null,
    tenant_id: "ten-0001",
    installation_id: "inst-0001",
    member_id: "mem-0001",
    installation_status: "active",
    installation_revoked_at: null,
    member_status: "active",
    tenant_status: "active",
    tenant_deleted_at: null,
    ...overrides,
  };
}

function resolves(...rows: TokenRow[]): void {
  query.mockResolvedValue({ rows });
}

describe("resolveTelemetryTokenByHash", () => {
  beforeEach(() => {
    query.mockReset();
  });

  it("정상 자격증명은 신원 4종을 그대로 매핑한다", async () => {
    resolves(row());

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: true,
      identity: {
        tokenId: "tok-0001",
        tenantId: "ten-0001",
        installationId: "inst-0001",
        memberId: "mem-0001",
      },
    });
  });

  it("토큰 해시를 바인드 파라미터로 넘긴다(문자열 보간이 아니다)", async () => {
    resolves(row());

    await resolveTelemetryTokenByHash("deadbeef");

    expect(query).toHaveBeenCalledTimes(1);
    expect(query.mock.calls[0]?.[1]).toEqual(["deadbeef"]);
    expect(query.mock.calls[0]?.[0]).not.toContain("deadbeef");
  });

  // ── 거부 사유 9종 ─────────────────────────────────────────────────────────
  // 9종 전부가 HTTP 로는 동일한 401 + "Invalid or expired credential" 이 된다.
  // 사유는 response.locals.authReason 에만 남으므로 블랙박스로는 구분할 수 없다.
  // 그래서 리포지토리를 직접 불러 사유를 고정한다.

  it("token_unknown — 해시에 걸리는 행이 없다", async () => {
    resolves();

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: false,
      reason: "token_unknown",
    });
  });

  const rejections: ReadonlyArray<[string, Partial<TokenRow>]> = [
    ["token_revoked", { token_revoked_at: REVOKED_AT }],
    ["installation_revoked", { installation_revoked_at: REVOKED_AT }],
    ["installation_inactive", { installation_status: "revoked" }],
    ["member_suspended", { member_status: "suspended" }],
    ["member_invited", { member_status: "invited" }],
    ["tenant_deleted", { tenant_deleted_at: REVOKED_AT }],
    ["tenant_suspended", { tenant_status: "suspended" }],
    ["tenant_terminated", { tenant_status: "terminated" }],
  ];

  it.each(rejections)("%s 로 거부한다", async (reason, broken) => {
    resolves(row(broken));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: false,
      reason,
    });
  });

  // ── 판정 순서 ────────────────────────────────────────────────────────────
  // if 체인의 순서 자체가 사양이다. 여러 조건이 동시에 참일 때 어느 사유가
  // 이기는지를 고정한다 — 순서를 바꾸면 운영에서 원인 분류가 통째로 달라진다.

  it("전부 무너진 행은 첫 검사인 token_revoked 로 떨어진다", async () => {
    resolves(
      row({
        token_revoked_at: REVOKED_AT,
        installation_revoked_at: REVOKED_AT,
        installation_status: "revoked",
        member_status: "suspended",
        tenant_status: "terminated",
        tenant_deleted_at: REVOKED_AT,
      }),
    );

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: false,
      reason: "token_revoked",
    });
  });

  const precedence: ReadonlyArray<[string, Partial<TokenRow>]> = [
    // 토큰 폐기가 설치 폐기를 이긴다.
    ["token_revoked", {
      token_revoked_at: REVOKED_AT,
      installation_revoked_at: REVOKED_AT,
    }],
    // 설치 폐기가 설치 비활성을 이긴다.
    ["installation_revoked", {
      installation_revoked_at: REVOKED_AT,
      installation_status: "revoked",
    }],
    // 설치 비활성이 구성원 상태를 이긴다.
    ["installation_inactive", {
      installation_status: "pending",
      member_status: "suspended",
    }],
    // 구성원 정지가 테넌트 삭제를 이긴다.
    ["member_suspended", {
      member_status: "suspended",
      tenant_deleted_at: REVOKED_AT,
    }],
    // 구성원 초대중이 테넌트 삭제를 이긴다.
    ["member_invited", {
      member_status: "invited",
      tenant_deleted_at: REVOKED_AT,
    }],
    // 테넌트 삭제가 테넌트 정지를 이긴다.
    ["tenant_deleted", {
      tenant_deleted_at: REVOKED_AT,
      tenant_status: "suspended",
    }],
  ];

  it.each(precedence)("동시 위반 시 %s 가 이긴다", async (reason, broken) => {
    resolves(row(broken));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: false,
      reason,
    });
  });

  // ── 통과하는 값들 (현행 동작 그대로 고정) ────────────────────────────────

  it("installation_status 는 'active' 만 통과한다", async () => {
    resolves(row({ installation_status: "ACTIVE" }));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toEqual({
      ok: false,
      reason: "installation_inactive",
    });
  });

  it("member_status 는 suspended·invited 만 막고 그 밖의 값은 통과시킨다", async () => {
    resolves(row({ member_status: "deactivated" }));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toMatchObject({
      ok: true,
    });
  });

  it("tenant_status 는 suspended·terminated 만 막고 그 밖의 값은 통과시킨다", async () => {
    resolves(row({ tenant_status: "trial" }));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toMatchObject({
      ok: true,
    });
  });

  it("행이 여러 개면 첫 행만 본다(SQL 의 LIMIT 1 과 같은 결과)", async () => {
    resolves(row({ token_id: "first" }), row({ token_id: "second" }));

    await expect(resolveTelemetryTokenByHash("hash")).resolves.toMatchObject({
      ok: true,
      identity: { tokenId: "first" },
    });
  });

  it("DB 오류는 삼키지 않고 그대로 던진다", async () => {
    query.mockRejectedValue(new Error("connection terminated"));

    await expect(resolveTelemetryTokenByHash("hash")).rejects.toThrow(
      "connection terminated",
    );
  });
});
