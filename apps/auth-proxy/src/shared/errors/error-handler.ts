import type { ErrorRequestHandler } from "express";
import { logger } from "../logging/logger.js";
import { AppError } from "./app-error.js";

export const errorHandler: ErrorRequestHandler = (
  error,
  _request,
  response,
  _next,
) => {
  if (error instanceof AppError) {
    response.locals.errorCode = error.code;
    if (error.outcome) response.locals.outcome = error.outcome;
    response
      .status(error.statusCode)
      .json({ error: error.code, message: error.message });
    return;
  }

  response.locals.errorCode = "internal_error";
  logger.error("unhandled_error", {
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
  });
  response
    .status(500)
    .json({ error: "internal_error", message: "Internal server error" });
};
