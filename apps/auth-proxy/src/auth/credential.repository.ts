import { postgres } from "../database/postgres.js";
import type { TelemetryTokenIdentity } from "./credential.types.js";

interface TelemetryTokenRow {
  token_id: string;
  tenant_id: string;
  installation_id: string;
  member_id: string;
}

export async function findActiveTelemetryTokenByHash(
  tokenHash: string,
): Promise<TelemetryTokenIdentity | null> {
  const result = await postgres.query<TelemetryTokenRow>(
    `SELECT tt.id AS token_id,
            i.tenant_id,
            i.id AS installation_id,
            i.member_id
       FROM enrollment.telemetry_tokens AS tt
       JOIN enrollment.installations AS i ON i.id = tt.installation_id
       JOIN enrollment.members AS m ON m.id = i.member_id
       JOIN enrollment.tenants AS t ON t.id = i.tenant_id
      WHERE tt.token_hash = $1
        AND tt.revoked_at IS NULL
        AND i.revoked_at IS NULL
        AND i.status = 'active'
        AND m.status = 'active'
        AND t.deleted_at IS NULL
        AND t.status = 'active'
      LIMIT 1`,
    [tokenHash],
  );
  const row = result.rows[0];
  return row
    ? {
        tokenId: row.token_id,
        tenantId: row.tenant_id,
        installationId: row.installation_id,
        memberId: row.member_id,
      }
    : null;
}
