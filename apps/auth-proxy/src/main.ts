import { createServer } from "node:http";
import { createApp } from "./app.js";
import { env } from "./config/env.js";
import { closePostgres } from "./database/postgres.js";
import { logger } from "./shared/logging/logger.js";

const server = createServer(createApp());
server.listen(env.port, () =>
  logger.info("server_started", { port: env.port, logLevel: env.logLevel }),
);

async function shutdown(signal: string): Promise<void> {
  logger.info("server_stopping", { signal });
  server.close(async () => {
    await closePostgres();
    process.exit(0);
  });
}

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
