import type { RequestHandler } from "express";
import { AppError } from "../shared/errors/app-error.js";
import { forwardToCollector } from "./collector.client.js";

export const proxyOtlp: RequestHandler = async (request, response) => {
  if (!request.auth)
    throw new AppError(
      401,
      "Authentication context is missing",
      "unauthorized",
    );
  if (!Buffer.isBuffer(request.body))
    throw new AppError(400, "OTLP body is required", "invalid_body");

  const upstream = await forwardToCollector(
    request.path,
    request.headers,
    request.body,
    request.auth,
  );
  upstream.headers.forEach((value, name) => response.setHeader(name, value));
  response.status(upstream.status).send(Buffer.from(upstream.body));
};
