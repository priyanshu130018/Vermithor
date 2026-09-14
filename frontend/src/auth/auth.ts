import { generateDevToken, getStoredToken, setStoredToken } from './token';

export async function getAuthHeader(): Promise<string> {
  let token = getStoredToken();
  if (!token) {
    token = await generateDevToken();
    setStoredToken(token);
  }
  return `Bearer ${token}`;
}
