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

declare global {
  namespace Express {
    interface Request {
      auth?: AuthContext;
    }
  }
}
