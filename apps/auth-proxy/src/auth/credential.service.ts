import { env } from "../config/env.js";
import { hashToken } from "../shared/crypto/token-hash.js";
import { findActiveTelemetryTokenByHash } from "./credential.repository.js";
import type { AuthContext } from "./credential.types.js";

export async function authenticateToken(token: string): Promise<AuthContext | null> {
  return findActiveTelemetryTokenByHash(hashToken(token, env.tokenHashSecret));
}
