import { postgres } from "../database/postgres.js";
import type { AuthResult } from "./credential.types.js";

interface TelemetryTokenRow {
  token_id: string;
  token_revoked_at: Date | null;
  tenant_id: string;
  installation_id: string;
  member_id: string;
  installation_status: string;
  installation_revoked_at: Date | null;
  member_status: string;
  tenant_status: string;
  tenant_deleted_at: Date | null;
}

export async function resolveTelemetryTokenByHash(
  tokenHash: string,
): Promise<AuthResult> {
  const result = await postgres.query<TelemetryTokenRow>(
    `SELECT tt.id AS token_id,
            tt.revoked_at AS token_revoked_at,
            i.tenant_id,
            i.id AS installation_id,
            i.member_id,
            i.status AS installation_status,
            i.revoked_at AS installation_revoked_at,
            m.status AS member_status,
            t.status AS tenant_status,
            t.deleted_at AS tenant_deleted_at
       FROM enrollment.telemetry_tokens AS tt
       JOIN enrollment.installations AS i ON i.id = tt.installation_id
       JOIN enrollment.members AS m ON m.id = i.member_id
       JOIN enrollment.tenants AS t ON t.id = i.tenant_id
      WHERE tt.token_hash = $1
      LIMIT 1`,
    [tokenHash],
  );

  const row = result.rows[0];
  if (!row) return { ok: false, reason: "token_unknown" };
  if (row.token_revoked_at !== null)
    return { ok: false, reason: "token_revoked" };
  if (row.installation_revoked_at !== null)
    return { ok: false, reason: "installation_revoked" };
  if (row.installation_status !== "active")
    return { ok: false, reason: "installation_inactive" };
  if (row.member_status === "suspended")
    return { ok: false, reason: "member_suspended" };
  if (row.member_status === "invited")
    return { ok: false, reason: "member_invited" };
  if (row.tenant_deleted_at !== null)
    return { ok: false, reason: "tenant_deleted" };
  if (row.tenant_status === "suspended")
    return { ok: false, reason: "tenant_suspended" };
  if (row.tenant_status === "terminated")
    return { ok: false, reason: "tenant_terminated" };

  return {
    ok: true,
    identity: {
      tokenId: row.token_id,
      tenantId: row.tenant_id,
      installationId: row.installation_id,
      memberId: row.member_id,
    },
  };
}
