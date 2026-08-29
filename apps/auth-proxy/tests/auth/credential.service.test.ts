import { beforeEach, describe, expect, it, vi } from "vitest";

const { resolveTelemetryTokenByHash } = vi.hoisted(() => ({
  resolveTelemetryTokenByHash: vi.fn(),
}));
vi.mock("../../src/auth/credential.repository.js", () => ({
  resolveTelemetryTokenByHash,
}));

import { authenticateToken } from "../../src/auth/credential.service.js";
import { hashToken } from "../../src/shared/crypto/token-hash.js";

// vitest.config.ts 가 러너에 주입하는 값과 같아야 한다.
const SECRET = "test-token-hash-secret";

describe("authenticateToken", () => {
  beforeEach(() => {
    resolveTelemetryTokenByHash.mockReset();
    resolveTelemetryTokenByHash.mockResolvedValue({ ok: false, reason: "token_unknown" });
  });

  it("평문 토큰이 아니라 HMAC 해시로 조회한다", async () => {
    await authenticateToken("pmt_live_example");

    expect(resolveTelemetryTokenByHash).toHaveBeenCalledWith(
      hashToken("pmt_live_example", SECRET),
    );
  });

  it("평문 토큰을 리포지토리에 넘기지 않는다", async () => {
    await authenticateToken("pmt_live_example");

    expect(resolveTelemetryTokenByHash).not.toHaveBeenCalledWith("pmt_live_example");
  });

  it("리포지토리 결과를 가공 없이 그대로 돌려준다", async () => {
    const result = { ok: true, identity: { tokenId: "t" } };
    resolveTelemetryTokenByHash.mockResolvedValue(result);

    await expect(authenticateToken("any")).resolves.toBe(result);
  });
});
