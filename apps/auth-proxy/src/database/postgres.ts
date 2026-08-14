import { Pool } from "pg";
import { env } from "../config/env.js";

export const postgres = new Pool({ connectionString: env.databaseUrl });

export async function closePostgres(): Promise<void> {
  await postgres.end();
}
