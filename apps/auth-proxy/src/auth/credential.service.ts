import { env } from "../config/env.js";
import { hashToken } from "../shared/crypto/token-hash.js";
import { resolveTelemetryTokenByHash } from "./credential.repository.js";
import type { AuthResult } from "./credential.types.js";

export async function authenticateToken(token: string): Promise<AuthResult> {
  return resolveTelemetryTokenByHash(hashToken(token, env.tokenHashSecret));
}
