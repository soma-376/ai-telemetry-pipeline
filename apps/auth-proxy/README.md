# Pulsemetry Auth Proxy

OTLP/HTTP 인증 프록시입니다. Bearer 토큰을 검증한 뒤 traces, metrics, logs 요청을 OpenTelemetry Collector로 전달합니다.

## Development

```sh
npm install
npm run dev
```

Bearer token은 `TOKEN_HASH_SECRET`을 사용해 HMAC-SHA256으로 해시한 뒤
`enrollment.telemetry_tokens`에서 조회합니다. 연결된 installation, member, tenant가
모두 활성 상태일 때만 Collector로 요청을 전달합니다.

## Endpoints

- `GET /health`
- `POST /v1/traces`
- `POST /v1/metrics`
- `POST /v1/logs`
