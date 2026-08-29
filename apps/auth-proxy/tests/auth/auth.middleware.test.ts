import type { NextFunction, Request, Response } from "express";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { authenticateToken } = vi.hoisted(() => ({
  authenticateToken: vi.fn(),
}));
vi.mock("../../src/auth/credential.service.js", () => ({ authenticateToken }));

import { authenticate } from "../../src/auth/auth.middleware.js";
import type { AuthFailureReason } from "../../src/auth/credential.types.js";
import { AppError } from "../../src/shared/errors/app-error.js";

const IDENTITY = {
  tokenId: "tok-0001",
  tenantId: "ten-0001",
  installationId: "inst-0001",
  memberId: "mem-0001",
};

function makeRequest(authorization?: string): Request {
  return {
    header(name: string): string | undefined {
      return name.toLowerCase() === "authorization" ? authorization : undefined;
    },
  } as unknown as Request;
}

function makeResponse(): Response {
  return { locals: {} } as unknown as Response;
}

interface Ran {
  request: Request;
  response: Response;
  next: NextFunction;
  error: unknown;
}

async function run(authorization?: string): Promise<Ran> {
  const request = makeRequest(authorization);
  const response = makeResponse();
  const calls: unknown[] = [];
  const next = vi.fn((error?: unknown) => {
    calls.push(error);
  }) as unknown as NextFunction;

  await authenticate(request, response, next);

  return { request, response, next, error: calls[0] };
}

describe("authenticate 미들웨어", () => {
  beforeEach(() => {
    authenticateToken.mockReset();
    authenticateToken.mockResolvedValue({ ok: true, identity: IDENTITY });
  });

  it("성공하면 request.auth 에 신원을 싣고 오류 없이 통과시킨다", async () => {
    const { request, next, error } = await run("Bearer tok-secret");

    expect(error).toBeUndefined();
    expect(next).toHaveBeenCalledTimes(1);
    expect(request.auth).toEqual(IDENTITY);
    expect(authenticateToken).toHaveBeenCalledWith("tok-secret");
  });

  it("Bearer 스킴은 대소문자를 가리지 않는다", async () => {
    await run("bearer tok-secret");

    expect(authenticateToken).toHaveBeenCalledWith("tok-secret");
  });

  it("스킴과 토큰 사이 공백은 여러 개여도 된다", async () => {
    await run("Bearer   tok-secret");

    expect(authenticateToken).toHaveBeenCalledWith("tok-secret");
  });

  // ── 미들웨어가 만드는 거부 사유 2종 ──────────────────────────────────────

  it("missing_bearer — Authorization 헤더가 없다", async () => {
    const { response, error } = await run(undefined);

    expect(response.locals.authReason).toBe("missing_bearer");
    expect(error).toBeInstanceOf(AppError);
    expect(authenticateToken).not.toHaveBeenCalled();
  });

  it("missing_bearer — 빈 문자열 헤더도 '없음'으로 본다", async () => {
    const { response } = await run("");

    expect(response.locals.authReason).toBe("missing_bearer");
  });

  it.each([
    ["스킴이 다르다", "Token tok-secret"],
    ["토큰이 없다", "Bearer"],
    ["공백만 있다", "Bearer "],
    ["토큰에 공백이 섞였다", "Bearer tok secret"],
    ["스킴이 붙어 있다", "Bearertok-secret"],
  ])("malformed_bearer — %s", async (_label, header) => {
    const { response, error } = await run(header);

    expect(response.locals.authReason).toBe("malformed_bearer");
    expect(error).toBeInstanceOf(AppError);
    expect(authenticateToken).not.toHaveBeenCalled();
  });

  // ── 리포지토리 사유 9종의 전달 ───────────────────────────────────────────

  const repositoryReasons: readonly AuthFailureReason[] = [
    "token_unknown",
    "token_revoked",
    "installation_revoked",
    "installation_inactive",
    "member_suspended",
    "member_invited",
    "tenant_deleted",
    "tenant_suspended",
    "tenant_terminated",
  ];

  it.each(repositoryReasons)(
    "%s 를 그대로 response.locals.authReason 에 남긴다",
    async (reason) => {
      authenticateToken.mockResolvedValue({ ok: false, reason });

      const { request, response } = await run("Bearer tok-secret");

      expect(response.locals.authReason).toBe(reason);
      expect(request.auth).toBeUndefined();
    },
  );

  it("거부 사유 11종이 전부 같은 401 응답으로 뭉개진다", async () => {
    const seen = new Set<string>();

    for (const reason of repositoryReasons) {
      authenticateToken.mockResolvedValue({ ok: false, reason });
      const { error } = await run("Bearer tok-secret");
      const appError = error as AppError;
      seen.add(
        JSON.stringify([
          appError.statusCode,
          appError.message,
          appError.code,
          appError.outcome,
        ]),
      );
    }
    for (const header of [undefined, "Token x"]) {
      const { error } = await run(header);
      const appError = error as AppError;
      seen.add(
        JSON.stringify([
          appError.statusCode,
          appError.message,
          appError.code,
          appError.outcome,
        ]),
      );
    }

    // 사유는 11가지지만 클라이언트가 보는 응답은 하나뿐이다 — 열거 공격 방지.
    expect([...seen]).toEqual([
      JSON.stringify([401, "Invalid or expired credential", "unauthorized", "rejected"]),
    ]);
  });
});
