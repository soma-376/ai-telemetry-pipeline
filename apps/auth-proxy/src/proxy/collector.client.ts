import { env } from "../config/env.js";
import type { AuthContext } from "../auth/credential.types.js";

const forwardedRequestHeaders = [
  "content-type",
  "content-encoding",
  "accept",
] as const;
const forwardedResponseHeaders = [
  "content-type",
  "content-encoding",
  "retry-after",
] as const;

export type ForwardResult =
  | { ok: true; status: number; headers: Headers; body: ArrayBuffer }
  | { ok: false; cause: "upstream_timeout" | "upstream_unreachable" };

export async function forwardToCollector(
  path: string,
  requestHeaders: Record<string, string | string[] | undefined>,
  body: Buffer,
  auth: AuthContext,
): Promise<ForwardResult> {
  const headers = new Headers();
  for (const name of forwardedRequestHeaders) {
    const value = requestHeaders[name];
    if (typeof value === "string") headers.set(name, value);
  }
  headers.set("x-pulsemetry-token-id", auth.tokenId);
  headers.set("x-pulsemetry-tenant-id", auth.tenantId);
  headers.set("x-pulsemetry-installation-id", auth.installationId);
  headers.set("x-pulsemetry-member-id", auth.memberId);

  try {
    const upstream = await fetch(`${env.collectorBaseUrl}${path}`, {
      method: "POST",
      headers,
      body: new Uint8Array(body),
      signal: AbortSignal.timeout(10_000),
    });
    const responseBody = await upstream.arrayBuffer();
    const responseHeaders = new Headers();
    for (const name of forwardedResponseHeaders) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return {
      ok: true,
      status: upstream.status,
      headers: responseHeaders,
      body: responseBody,
    };
  } catch (error) {
    const cause =
      error instanceof Error && error.name === "TimeoutError"
        ? "upstream_timeout"
        : "upstream_unreachable";
    return { ok: false, cause };
  }
}
