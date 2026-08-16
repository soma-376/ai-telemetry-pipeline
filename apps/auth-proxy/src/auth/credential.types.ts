export interface TelemetryTokenIdentity {
  tokenId: string;
  tenantId: string;
  installationId: string;
  memberId: string;
}

export interface AuthContext {
  tokenId: string;
  tenantId: string;
  installationId: string;
  memberId: string;
}

export type AuthFailureReason =
  | "missing_bearer"
  | "malformed_bearer"
  | "token_unknown"
  | "token_revoked"
  | "installation_revoked"
  | "installation_inactive"
  | "member_suspended"
  | "member_invited"
  | "tenant_suspended"
  | "tenant_terminated"
  | "tenant_deleted";

export type AuthResult =
  | { ok: true; identity: TelemetryTokenIdentity }
  | { ok: false; reason: AuthFailureReason };

declare global {
  namespace Express {
    interface Request {
      auth?: AuthContext;
    }
  }
}
