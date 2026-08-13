import { randomUUID } from "node:crypto";
import type { RequestHandler } from "express";
import { env } from "../config/env.js";

const observableHeaders = [
  "content-type",
  "content-encoding",
  "content-length",
  "user-agent",
  "x-forwarded-for",
  "x-forwarded-proto",
] as const;

export const requestLogger: RequestHandler = (request, response, next) => {
  if (!env.logRequestHeaders) return next();

  const requestId = request.header("x-request-id") ?? randomUUID();
  response.setHeader("x-request-id", requestId);
  const startedAt = performance.now();

  response.on("finish", () => {
    const headers = Object.fromEntries(
      observableHeaders.flatMap((name) => {
        const value = request.header(name);
        return value ? [[name, value]] : [];
      }),
    );

    console.info(JSON.stringify({
      event: "otlp_request",
      requestId,
      method: request.method,
      path: request.path,
      status: response.statusCode,
      durationMs: Math.round((performance.now() - startedAt) * 100) / 100,
      headers,
      auth: request.auth
        ? {
            tokenId: request.auth.tokenId,
            tenantId: request.auth.tenantId,
            installationId: request.auth.installationId,
            memberId: request.auth.memberId,
          }
        : null,
    }));
  });

  next();
};
