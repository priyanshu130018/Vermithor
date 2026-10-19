/**
 * Authentication Token Manager for Vermithor Frontend
 *
 * SECURITY POLICY:
 * In accordance with Vermithor security architecture, client-side signing of JWTs
 * is strictly prohibited in production. Secret keys (JWT_SECRET) must never be bundled
 * into client-side code or exposed via VITE_ environment variables.
 *
 * Tokens are securely issued by the backend authentication service and persisted
 * in browser storage. Every access token must contain valid claims:
 * - sub: Subject identifier (non-empty string)
 * - iss: Issuer identifier (must match backend JWT_ISSUER, default "vermithor")
 * - aud: Audience identifier (must match backend JWT_AUDIENCE, default "vermithor-api")
 * - exp: Expiration timestamp in the future
 */

export const TOKEN_KEY = 'vermithor_auth_token';

export const EXPECTED_JWT_ISSUER =
  (typeof window !== 'undefined' && (window as any).__ENV__?.VITE_JWT_ISSUER) ||
  import.meta.env.VITE_JWT_ISSUER ||
  'vermithor';

export const EXPECTED_JWT_AUDIENCE =
  (typeof window !== 'undefined' && (window as any).__ENV__?.VITE_JWT_AUDIENCE) ||
  import.meta.env.VITE_JWT_AUDIENCE ||
  'vermithor-api';

let inFlightTokenPromise: Promise<string> | null = null;

/**
 * Safely parse claims payload from an unverified JWT string.
 */
export function parseJwtPayload(token: string): Record<string, any> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    let b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    while (b64.length % 4 !== 0) {
      b64 += '=';
    }
    const json = decodeURIComponent(
      atob(b64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/**
 * Validate that an unverified token payload contains all required claims (sub, exp, iss, aud)
 * and conforms to expected issuer, audience, and expiration constraints.
 */
export function isTokenValid(
  token: string,
  leewaySeconds = 30,
  expectedIssuer: string = EXPECTED_JWT_ISSUER,
  expectedAudience: string = EXPECTED_JWT_AUDIENCE
): boolean {
  if (!token || typeof token !== 'string') {
    return false;
  }
  const payload = parseJwtPayload(token);
  if (!payload || typeof payload !== 'object') {
    return false;
  }

  // 1. Verify subject claim exists and is non-empty
  if (!payload.sub || typeof payload.sub !== 'string' || payload.sub.trim() === '') {
    return false;
  }

  // 2. Verify expiration claim exists and is in the future
  if (typeof payload.exp !== 'number') {
    return false;
  }
  const now = Math.floor(Date.now() / 1000);
  if (payload.exp <= now + leewaySeconds) {
    return false;
  }

  // 3. Verify issuer claim exists and matches expected issuer
  if (!payload.iss || typeof payload.iss !== 'string' || payload.iss !== expectedIssuer) {
    return false;
  }

  // 4. Verify audience claim exists and matches expected audience
  if (!payload.aud || typeof payload.aud !== 'string' || payload.aud !== expectedAudience) {
    return false;
  }

  return true;
}

/**
 * Check if the token has expired, is nearing expiration, or is missing required claims.
 */
export function isTokenExpired(token: string, leewaySeconds = 30): boolean {
  return !isTokenValid(token, leewaySeconds);
}

export function getStoredToken(): string | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const token = localStorage.getItem(TOKEN_KEY);
      if (token) {
        if (!isTokenValid(token)) {
          // Invalidate and purge tokens lacking required claims or past expiry
          localStorage.removeItem(TOKEN_KEY);
          return null;
        }
        return token;
      }
    }
  } catch {
    // Non-browser or restricted storage environment
  }
  return null;
}

export function setStoredToken(token: string): void {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.setItem(TOKEN_KEY, token);
    }
  } catch {
    // Non-browser or restricted storage environment
  }
}

export function clearStoredToken(): void {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // Non-browser or restricted storage environment
  }
}

/**
 * Acquire a server-signed development token from the backend authentication endpoint.
 * Uses singleton Promise deduplication to prevent redundant concurrent roundtrips.
 */
export async function fetchDevToken(): Promise<string> {
  if (inFlightTokenPromise) {
    return inFlightTokenPromise;
  }

  inFlightTokenPromise = (async () => {
    try {
      const baseUrl =
        (typeof window !== 'undefined' && (window as any).__ENV__?.VITE_API_BASE_URL) ||
        import.meta.env.VITE_API_BASE_URL ||
        'http://localhost:8080';

      const response = await fetch(`${baseUrl}/api/v1/auth/dev-token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to obtain development token (HTTP ${response.status})`);
      }

      const data = await response.json();
      const token = data.access_token;
      if (!token || typeof token !== 'string') {
        throw new Error('Malformed token response from authentication endpoint');
      }

      setStoredToken(token);
      return token;
    } finally {
      inFlightTokenPromise = null;
    }
  })();

  return inFlightTokenPromise;
}

/**
 * Backwards compatibility alias for development token acquisition.
 */
export async function generateDevToken(): Promise<string> {
  return fetchDevToken();
}
