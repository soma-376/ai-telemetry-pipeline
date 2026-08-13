function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function positiveInteger(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export const logLevels = ["silent", "error", "warn", "info", "debug"] as const;
export type LogLevel = (typeof logLevels)[number];

function logLevel(name: string, fallback: LogLevel): LogLevel {
  const raw = process.env[name];
  if (!raw) return fallback;
  if (!logLevels.includes(raw as LogLevel)) {
    throw new Error(`${name} must be one of: ${logLevels.join(", ")}`);
  }
  return raw as LogLevel;
}

export const env = Object.freeze({
  port: positiveInteger("PORT", 4316),
  collectorBaseUrl: required("COLLECTOR_BASE_URL").replace(/\/$/, ""),
  databaseUrl: required("DATABASE_URL"),
  tokenHashSecret: required("TOKEN_HASH_SECRET"),
  maxOtlpBodySize: positiveInteger("MAX_OTLP_BODY_SIZE", 10 * 1024 * 1024),
  logLevel: logLevel("LOG_LEVEL", "info"),
});
