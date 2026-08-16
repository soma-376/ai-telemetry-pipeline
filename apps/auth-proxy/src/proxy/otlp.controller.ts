import type { RequestHandler } from "express";
import { AppError } from "../shared/errors/app-error.js";
import { forwardToCollector } from "./collector.client.js";

export const proxyOtlp: RequestHandler = async (request, response) => {
  if (!request.auth)
    throw new AppError(
      401,
      "Authentication context is missing",
      "unauthorized",
      "rejected",
    );
  if (!Buffer.isBuffer(request.body))
    throw new AppError(
      400,
      "OTLP body is required",
      "invalid_body",
      "rejected",
    );

  const result = await forwardToCollector(
    request.path,
    request.headers,
    request.body,
    request.auth,
  );

  if (!result.ok) {
    response.locals.outcomeCause = result.cause;
    const status = result.cause === "upstream_timeout" ? 504 : 502;
    throw new AppError(
      status,
      "Telemetry collector unavailable",
      result.cause,
      "failed",
    );
  }

  response.locals.outcome = result.status < 400 ? "delivered" : "failed";
  if (result.status >= 400)
    response.locals.outcomeCause = `upstream_http_${result.status}`;
  result.headers.forEach((value, name) => response.setHeader(name, value));
  response.status(result.status).send(Buffer.from(result.body));
};
