import { randomUUID } from "node:crypto";
import type { Request, RequestHandler } from "express";
import { logger } from "./logger.js";

const observableHeaders = [
  "content-type",
  "content-encoding",
  "content-length",
  "user-agent",
  "x-forwarded-for",
  "x-forwarded-proto",
] as const;

function severityFor(status: number): "error" | "warn" | "info" {
  if (status >= 500) return "error";
  if (status >= 400) return "warn";
  return "info";
}

function collectHeaders(request: Request): Record<string, string> {
  return Object.fromEntries(
    observableHeaders.flatMap((name) => {
      const value = request.header(name);
      return value ? [[name, value]] : [];
    }),
  );
}

export const requestLogger: RequestHandler = (request, response, next) => {
  const requestId = request.header("x-request-id") ?? randomUUID();
  response.setHeader("x-request-id", requestId);
  const startedAt = performance.now();

  response.on("finish", () => {
    const errorCode = response.locals.errorCode as string | undefined;
    const authReason = response.locals.authReason as string | undefined;
    const outcome = response.locals.outcome as string | undefined;
    const outcomeCause = response.locals.outcomeCause as string | undefined;
    logger[severityFor(response.statusCode)]("otlp_request", {
      requestId,
      method: request.method,
      path: request.path,
      status: response.statusCode,
      durationMs: Math.round((performance.now() - startedAt) * 100) / 100,
      product: request.header("x-pulsemetry-product") ?? null,
      auth: request.auth
        ? {
            tokenId: request.auth.tokenId,
            tenantId: request.auth.tenantId,
            installationId: request.auth.installationId,
            memberId: request.auth.memberId,
          }
        : null,
      ...(outcome ? { outcome } : {}),
      ...(outcomeCause ? { outcomeCause } : {}),
      ...(errorCode ? { errorCode } : {}),
      ...(authReason ? { authReason } : {}),
      ...(logger.isDebug() ? { headers: collectHeaders(request) } : {}),
    });
  });

  next();
};
