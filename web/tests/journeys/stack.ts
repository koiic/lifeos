// The local stack the journeys run against (plan 6.1 `make verify-e2e`): a fresh PostgreSQL
// database, the API under uvicorn, and the built app served by `vite preview` with `/api`
// forwarded to the API, as the Pages Function does in production (ADR-0001).
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const API_PORT = 8001;
export const WEB_PORT = 4174;
// WebAuthn needs a secure context: http://localhost is one, and it is the relying party ID.
export const WEB_ORIGIN = `http://localhost:${String(WEB_PORT)}`;
export const E2E_DATABASE_URL = 'postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos_e2e';

export const SERVER_DIR = fileURLToPath(new URL('../../../server', import.meta.url));
export const STACK_SCRIPT = fileURLToPath(
  new URL('../../../scripts/e2e_stack.sh', import.meta.url),
);

export const STACK_ENV = {
  ENV: 'local',
  APP_ORIGIN: WEB_ORIGIN,
  DATABASE_URL: E2E_DATABASE_URL,
};

function serverScript(module: string, args: string[]): string {
  return execFileSync('uv', ['run', 'python', '-m', module, ...args], {
    cwd: SERVER_DIR,
    env: { ...process.env, ...STACK_ENV },
    encoding: 'utf8',
  }).trim();
}

/** Her sessions no longer count as recently authenticated (CR-017), as after 5 minutes. */
export function expireRecentAuth(email: string): void {
  serverScript('tests.e2e.expire_recent_auth', [email]);
}

/** A single-use invite created through the auth service, as the admin console will (T44). */
export function createInvite(email?: string): string {
  return serverScript('tests.e2e.invite', email ? [email] : []);
}
