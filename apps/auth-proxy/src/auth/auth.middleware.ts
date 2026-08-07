import type { RequestHandler } from "express";
import { AppError } from "../shared/errors/app-error.js";
import { authenticateToken } from "./credential.service.js";

export const authenticate: RequestHandler = async (
  request,
  _response,
  next,
) => {
  const authorization = request.header("authorization");
  const match = authorization?.match(/^Bearer\s+([^\s]+)$/i);
  if (!match?.[1])
    return next(
      new AppError(401, "A valid bearer token is required", "unauthorized"),
    );

  const auth = await authenticateToken(match[1]);
  if (!auth)
    return next(
      new AppError(401, "Invalid or expired credential", "unauthorized"),
    );
  request.auth = auth;
  next();
};
