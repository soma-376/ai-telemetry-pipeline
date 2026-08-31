import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";

import { hashToken } from "../../src/shared/crypto/token-hash.js";

// telemetry_token 해시는 HMAC-SHA256(TOKEN_HASH_SECRET) 이다. backend 가 발급할 때
// 같은 키·같은 연산을 쓰므로, 이 벡터가 바뀌면 이미 발급된 토큰이 전부 조회 불가가 된다.
// 상수는 하드코딩된 기대값으로 고정한다 — 구현을 다시 불러 비교하면 회귀를 못 잡는다.
describe("hashToken", () => {
  it("고정 입력에 대해 알려진 HMAC-SHA256 hex 를 낸다", () => {
    expect(hashToken("pmt_live_example", "test-token-hash-secret")).toBe(
      "1173f322abc6c42104fccdd578658dbe7fe0c854f817660b812c5e97f21db94d",
    );
  });

  it("64자 소문자 hex 를 낸다", () => {
    expect(hashToken("any-token", "any-secret")).toMatch(/^[0-9a-f]{64}$/);
  });

  it("같은 입력은 항상 같은 해시다(무염 · 결정적)", () => {
    expect(hashToken("pmt_live_example", "s")).toBe(
      hashToken("pmt_live_example", "s"),
    );
  });

  it("키가 다르면 해시가 다르다", () => {
    expect(hashToken("t", "secret-a")).not.toBe(hashToken("t", "secret-b"));
  });

  it("토큰이 다르면 해시가 다르다", () => {
    expect(hashToken("token-a", "s")).not.toBe(hashToken("token-b", "s"));
  });

  it("UTF-8 로 인코딩한다(비ASCII 토큰도 latin1 이 아니다)", () => {
    const token = "토큰-✓";
    const expected = createHmac("sha256", "s")
      .update(Buffer.from(token, "utf8"))
      .digest("hex");
    expect(hashToken(token, "s")).toBe(expected);
  });

  it("빈 토큰도 거부하지 않고 해시한다(검증은 상위 계층 몫)", () => {
    expect(hashToken("", "s")).toMatch(/^[0-9a-f]{64}$/);
  });
});
