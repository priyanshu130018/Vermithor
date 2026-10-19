import { fetchDevToken, getStoredToken, isTokenExpired, clearStoredToken } from './token';

/**
 * Return formatted HTTP Authorization header with Bearer token.
 * Validates token expiration and automatically acquires a fresh development token if needed.
 */
export async function getAuthHeader(): Promise<string> {
  let token = getStoredToken();
  if (token && isTokenExpired(token)) {
    clearStoredToken();
    token = null;
  }

  if (!token) {
    try {
      token = await fetchDevToken();
    } catch (err) {
      // In offline/mock test environments, log warning without crashing
      console.warn('Could not acquire development auth token:', err);
      return '';
    }
  }

  return token ? `Bearer ${token}` : '';
}

export function clearAuth(): void {
  clearStoredToken();
}
