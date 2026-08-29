import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // src/config/env.ts 는 모듈 최상위에서 즉시 평가되며 필수 변수가 없으면
    // import 시점에 throw 한다. 테스트 파일이 무엇을 import 하든 안전하도록
    // 러너 레벨에서 미리 주입한다.
    env: {
      COLLECTOR_BASE_URL: "http://collector.test:4318/",
      DATABASE_URL: "postgres://test:test@localhost:5432/test",
      TOKEN_HASH_SECRET: "test-token-hash-secret",
    },
  },
});
