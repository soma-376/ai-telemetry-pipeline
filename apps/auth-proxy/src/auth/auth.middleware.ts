import type { NextFunction, RequestHandler, Response } from "express";
import { AppError } from "../shared/errors/app-error.js";
import { authenticateToken } from "./credential.service.js";
import type { AuthFailureReason } from "./credential.types.js";

function reject(
  response: Response,
  next: NextFunction,
  reason: AuthFailureReason,
): void {
  response.locals.authReason = reason;
  next(
    new AppError(
      401,
      "Invalid or expired credential",
      "unauthorized",
      "rejected",
    ),
  );
}

export const authenticate: RequestHandler = async (request, response, next) => {
  const authorization = request.header("authorization");
  if (!authorization) return reject(response, next, "missing_bearer");

  const match = authorization.match(/^Bearer\s+([^\s]+)$/i);
  if (!match?.[1]) return reject(response, next, "malformed_bearer");

  const result = await authenticateToken(match[1]);
  if (!result.ok) return reject(response, next, result.reason);

  request.auth = result.identity;
  next();
};
