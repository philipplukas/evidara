/** Types for playwright-server-identity.mjs (consumed by both Playwright configs). */

export interface IdentityTarget {
  url: string;
  surface: string;
}

export interface IdentityPayload {
  surface: string;
  runId: string;
  pid: number;
  startedAt: string;
}

export declare const IDENTITY_PATH: string;
export declare function reuseExistingServer(): boolean;
export declare function ensureRunId(): string;
export declare function declareIdentityTargets(targets: IdentityTarget[]): IdentityTarget[];
export declare function assertServerIdentity(
  target: IdentityTarget,
  options: { expectedRunId: string; enforceRunId: boolean; timeoutMs?: number },
): Promise<IdentityPayload>;
declare const globalSetup: () => Promise<void>;
export default globalSetup;
