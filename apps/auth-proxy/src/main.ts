import { createServer } from "node:http";
import { createApp } from "./app.js";
import { env } from "./config/env.js";
import { closePostgres } from "./database/postgres.js";

const server = createServer(createApp());
server.listen(env.port, () => console.log(`pulsemetry-auth-proxy listening on :${env.port}`));

async function shutdown(signal: string): Promise<void> {
  console.log(`${signal} received, shutting down`);
  server.close(async () => {
    await closePostgres();
    process.exit(0);
  });
}

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
