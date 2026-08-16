import { Router, type RequestHandler } from "express";
import { env } from "../config/env.js";
import { authenticate } from "../auth/auth.middleware.js";
import { AppError } from "../shared/errors/app-error.js";
import { proxyOtlp } from "./otlp.controller.js";

export const otlpRouter = Router();

const parseOtlpBody: RequestHandler = async (request, _response, next) => {
  try {
    const contentLength = Number(request.header("content-length") ?? 0);
    if (contentLength > env.maxOtlpBodySize) {
      throw new AppError(413, "OTLP body is too large", "payload_too_large");
    }

    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of request) {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      size += buffer.length;
      if (size > env.maxOtlpBodySize) {
        throw new AppError(413, "OTLP body is too large", "payload_too_large");
      }
      chunks.push(buffer);
    }
    request.body = Buffer.concat(chunks, size);
    next();
  } catch (error) {
    next(error);
  }
};

otlpRouter.post(
  ["/v1/traces", "/v1/metrics", "/v1/logs"],
  authenticate,
  parseOtlpBody,
  proxyOtlp,
);
