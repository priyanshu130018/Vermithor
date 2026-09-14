/**
 * Authentication Token Manager for Vermithor Frontend
 *
 * SECURITY NOTICE:
 * In production deployments, client-side signing is strictly prohibited.
 * Tokens must be issued by a trusted authentication service / IdP and injected
 * into storage or session cookies.
 */

const TOKEN_KEY = 'vermithor_auth_token';

// Development-only configurable secret (Never used in production)
const DEV_SECRET = import.meta.env.VITE_JWT_SECRET || 'vermithor-dev-secret-key-32-chars-min';

function base64url(source: string): string {
  const encodedSource = btoa(source);
  return encodedSource.replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
}

async function hmacSha256(key: string, data: string): Promise<string> {
  const enc = new TextEncoder();
  const cryptoKey = await window.crypto.subtle.importKey(
    'raw',
    enc.encode(key),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await window.crypto.subtle.sign('HMAC', cryptoKey, enc.encode(data));
  const binary = String.fromCharCode(...new Uint8Array(signature));
  return base64url(binary);
}

/**
 * [DEVELOPMENT ONLY] Generates an ephemeral token for local sandbox testing.
 * Gated to non-production environments.
 */
export async function generateDevToken(): Promise<string> {
  if (import.meta.env.PROD) {
    throw new Error('Local dev token generation is disabled in production environments.');
  }

  const header = { alg: 'HS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: 'sre-user-001',
    name: 'Incident Commander',
    iss: import.meta.env.VITE_JWT_ISSUER || 'vermithor',
    aud: import.meta.env.VITE_JWT_AUDIENCE || 'vermithor-api',
    iat: now,
    exp: now + 3600 * 24, // 24 hours
  };

  const headerB64 = base64url(JSON.stringify(header));
  const payloadB64 = base64url(JSON.stringify(payload));
  const signature = await hmacSha256(DEV_SECRET, `${headerB64}.${payloadB64}`);

  return `${headerB64}.${payloadB64}.${signature}`;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}
