import express from "express";
import { healthRouter } from "./health/health.routes.js";
import { otlpRouter } from "./proxy/otlp.routes.js";
import { errorHandler } from "./shared/errors/error-handler.js";
import { requestLogger } from "./shared/logging/request-logger.js";

export function createApp(): express.Express {
  const app = express();
  app.disable("x-powered-by");
  app.use(requestLogger);
  app.use(healthRouter);
  app.use(otlpRouter);
  app.use(errorHandler);
  return app;
}
