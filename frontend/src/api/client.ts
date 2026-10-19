import axios from 'axios';
import { getAuthHeader } from '../auth/auth';
import { clearStoredToken } from '../auth/token';

// Single Gateway Base URL (supports optional runtime injection, build-time env, or local gateway default)
export const API_BASE_URL =
  (typeof window !== 'undefined' && (window as any).__ENV__?.VITE_API_BASE_URL) ||
  import.meta.env.VITE_API_BASE_URL ||
  'http://localhost:8080';

export function createApiClient(baseURL: string = API_BASE_URL) {
  const client = axios.create({
    baseURL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Attach JWT Bearer Token and Request-ID
  client.interceptors.request.use(async (config) => {
    try {
      if (typeof window !== 'undefined') {
        const authHeader = await getAuthHeader();
        if (authHeader) {
          if (config.headers.set) {
            config.headers.set('Authorization', authHeader);
          } else {
            config.headers['Authorization'] = authHeader;
          }
        }
      }
    } catch {
      // Fallback in non-browser/test environments
    }

    if (!config.headers['X-Request-ID']) {
      const reqId = `req-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      if (config.headers.set) {
        config.headers.set('X-Request-ID', reqId);
      } else {
        config.headers['X-Request-ID'] = reqId;
      }
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest = error?.config;
      // When server returns 401 Unauthorized, clear any stale or invalidated token and retry once
      if (error?.response?.status === 401 && originalRequest && !originalRequest._retry) {
        originalRequest._retry = true;
        clearStoredToken();
        try {
          const authHeader = await getAuthHeader();
          if (authHeader) {
            if (originalRequest.headers?.set) {
              originalRequest.headers.set('Authorization', authHeader);
            } else {
              originalRequest.headers = originalRequest.headers || {};
              originalRequest.headers['Authorization'] = authHeader;
            }
            return client(originalRequest);
          }
        } catch {
          // If retry fails, fall through to rejection
        }
      } else if (error?.response?.status === 401) {
        clearStoredToken();
      }

      const message =
        error?.response?.data?.message ||
        error?.response?.data?.detail ||
        error?.message ||
        'An unexpected error occurred';
      return Promise.reject(new Error(message));
    }
  );

  return client;
}

// All API clients route through the unified gateway on :8080
export const gatewayApi = createApiClient(API_BASE_URL);
export const incidentApi = gatewayApi;
export const anomalyApi = gatewayApi;
export const correlationApi = gatewayApi;
export const rcaApi = gatewayApi;
export const logApi = gatewayApi;
export const retrievalApi = gatewayApi;
export const summaryApi = gatewayApi;
export const ingestionApi = gatewayApi;
export const agentApi = gatewayApi;
export const apiClient = gatewayApi;
