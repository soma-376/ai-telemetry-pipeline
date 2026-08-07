import { createHmac } from "node:crypto";

export function hashToken(token: string, secret: string): string {
  return createHmac("sha256", secret).update(token, "utf8").digest("hex");
}
