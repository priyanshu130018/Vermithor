import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  TOKEN_KEY,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
  parseJwtPayload,
  isTokenValid,
  isTokenExpired,
  fetchDevToken,
  EXPECTED_JWT_ISSUER,
  EXPECTED_JWT_AUDIENCE,
} from '../auth/token';
import { getAuthHeader, clearAuth } from '../auth/auth';
import { createApiClient } from '../api/client';

function createMockJwt(claims: Record<string, any>): string {
  const header = { alg: 'HS256', typ: 'JWT' };
  const hB64 = btoa(JSON.stringify(header)).replace(/=/g, '');
  const pB64 = btoa(JSON.stringify(claims)).replace(/=/g, '');
  return `${hB64}.${pB64}.fakesignature123`;
}

describe('Auth and Token Utilities', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('manages valid token storage lifecycle in localStorage', () => {
    const now = Math.floor(Date.now() / 1000);
    const validToken = createMockJwt({
      sub: 'sre-user-001',
      iss: EXPECTED_JWT_ISSUER,
      aud: EXPECTED_JWT_AUDIENCE,
      exp: now + 3600,
    });

    expect(getStoredToken()).toBeNull();
    setStoredToken(validToken);
    expect(getStoredToken()).toBe(validToken);
    expect(localStorage.getItem(TOKEN_KEY)).toBe(validToken);
    clearStoredToken();
    expect(getStoredToken()).toBeNull();
  });

  it('purges stored tokens that lack iss or aud claims', () => {
    const now = Math.floor(Date.now() / 1000);
    // Token with sub, exp, iat but NO iss or aud
    const legacyTokenNoIssAud = createMockJwt({
      sub: 'sre-user-001',
      iat: now,
      exp: now + 3600,
    });

    setStoredToken(legacyTokenNoIssAud);
    expect(localStorage.getItem(TOKEN_KEY)).toBe(legacyTokenNoIssAud);

    // getStoredToken should identify missing iss/aud, purge it, and return null
    expect(getStoredToken()).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('correctly validates required claims (sub, exp, iss, aud)', () => {
    const now = Math.floor(Date.now() / 1000);

    // Fully valid token
    const validToken = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now + 3600,
    });
    expect(isTokenValid(validToken)).toBe(true);
    expect(isTokenExpired(validToken)).toBe(false);

    // Missing iss
    const missingIss = createMockJwt({
      sub: 'sre-user-001',
      aud: 'vermithor-api',
      exp: now + 3600,
    });
    expect(isTokenValid(missingIss)).toBe(false);
    expect(isTokenExpired(missingIss)).toBe(true);

    // Missing aud
    const missingAud = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      exp: now + 3600,
    });
    expect(isTokenValid(missingAud)).toBe(false);
    expect(isTokenExpired(missingAud)).toBe(true);

    // Wrong issuer
    const wrongIss = createMockJwt({
      sub: 'sre-user-001',
      iss: 'unauthorized-iss',
      aud: 'vermithor-api',
      exp: now + 3600,
    });
    expect(isTokenValid(wrongIss)).toBe(false);

    // Wrong audience
    const wrongAud = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'unauthorized-aud',
      exp: now + 3600,
    });
    expect(isTokenValid(wrongAud)).toBe(false);

    // Expired
    const expiredToken = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now - 3600,
    });
    expect(isTokenValid(expiredToken)).toBe(false);
    expect(isTokenExpired(expiredToken)).toBe(true);

    // Malformed token
    expect(parseJwtPayload('invalid-jwt-token')).toBeNull();
    expect(isTokenValid('invalid-jwt-token')).toBe(false);
  });

  it('fetches server-signed development token and caches in localStorage', async () => {
    const now = Math.floor(Date.now() / 1000);
    const mockJwt = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now + 86400,
    });

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: mockJwt,
        token_type: 'Bearer',
        expires_in: 86400,
        user: { sub: 'sre-user-001' },
      }),
    } as any);

    const token = await fetchDevToken();
    expect(token).toBe(mockJwt);
    expect(getStoredToken()).toBe(mockJwt);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/dev-token'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('automatically acquires a fresh server token when stored token is missing iss/aud', async () => {
    const now = Math.floor(Date.now() / 1000);
    // Legacy token missing iss and aud
    const legacyToken = createMockJwt({ sub: 'sre-user-001', exp: now + 3600, iat: now });
    localStorage.setItem(TOKEN_KEY, legacyToken);

    const freshValidToken = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now + 3600,
    });

    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: freshValidToken }),
    } as any);

    const header = await getAuthHeader();
    expect(header).toBe(`Bearer ${freshValidToken}`);
    expect(getStoredToken()).toBe(freshValidToken);
  });

  it('injects Authorization and X-Request-ID headers into Axios requests', async () => {
    const now = Math.floor(Date.now() / 1000);
    const validToken = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now + 3600,
    });
    setStoredToken(validToken);

    const client = createApiClient('http://localhost:8080');

    // Invoke interceptor chain
    const requestHandler = (client.interceptors.request as any).handlers[0].fulfilled;
    const initialConfig = { headers: {} as Record<string, string> };
    const processed = await requestHandler(initialConfig);

    expect(processed.headers['Authorization']).toBe(`Bearer ${validToken}`);
    expect(processed.headers['X-Request-ID']).toMatch(/^req-\d+-[a-z0-9]+$/);
  });

  it('clears stored token and handles 401 error', async () => {
    const now = Math.floor(Date.now() / 1000);
    const validToken = createMockJwt({
      sub: 'sre-user-001',
      iss: 'vermithor',
      aud: 'vermithor-api',
      exp: now + 3600,
    });
    setStoredToken(validToken);
    expect(getStoredToken()).toBe(validToken);

    const client = createApiClient('http://localhost:8080');
    const errorHandler = (client.interceptors.response as any).handlers[0].rejected;

    const error401 = {
      response: {
        status: 401,
        data: { message: 'Invalid authentication token' },
      },
      config: { _retry: true, headers: {} },
    };

    await expect(errorHandler(error401)).rejects.toThrow('Invalid authentication token');
    expect(getStoredToken()).toBeNull();
  });
});
