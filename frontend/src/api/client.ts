import axios from 'axios';
import { getAuthHeader } from '../auth/auth';

// Single Gateway Base URL
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

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
      if (typeof window !== 'undefined' && window.crypto?.subtle) {
        const authHeader = await getAuthHeader();
        config.headers['Authorization'] = authHeader;
      }
    } catch {
      // Fallback in non-browser/test environments
    }

    if (!config.headers['X-Request-ID']) {
      config.headers['X-Request-ID'] = `req-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      const message = error.response?.data?.message || error.response?.data?.detail || error.message || 'An unexpected error occurred';
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
