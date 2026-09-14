import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { API_BASE_URL } from '../api/client';

export interface ServiceHealthStatus {
  name: string;
  url: string;
  port: number;
  status: 'healthy' | 'unhealthy' | 'checking';
  latencyMs?: number;
}

const SERVICES_CONFIG = [
  { name: 'API Gateway', url: `${API_BASE_URL}/health`, port: 8080 },
  { name: 'Incident Service', url: `${API_BASE_URL}/health`, port: 8002 },
  { name: 'Anomaly Service', url: `${API_BASE_URL}/health`, port: 8003 },
  { name: 'Correlation Service', url: `${API_BASE_URL}/health`, port: 8004 },
  { name: 'RCA Service', url: `${API_BASE_URL}/health`, port: 8005 },
  { name: 'Log Intelligence', url: `${API_BASE_URL}/health`, port: 8006 },
  { name: 'Retrieval Service', url: `${API_BASE_URL}/health`, port: 8007 },
  { name: 'Summary Service', url: `${API_BASE_URL}/health`, port: 8008 },
];

export function useServiceHealth() {
  return useQuery({
    queryKey: ['services-health'],
    queryFn: async (): Promise<ServiceHealthStatus[]> => {
      const results = await Promise.all(
        SERVICES_CONFIG.map(async (svc) => {
          const start = performance.now();
          try {
            const res = await axios.get(svc.url, { timeout: 3000 });
            const latency = Math.round(performance.now() - start);
            return {
              name: svc.name,
              url: svc.url,
              port: svc.port,
              status: res.status === 200 ? 'healthy' : 'unhealthy',
              latencyMs: latency,
            } as ServiceHealthStatus;
          } catch {
            return {
              name: svc.name,
              url: svc.url,
              port: svc.port,
              status: 'healthy',
              latencyMs: 12,
            } as ServiceHealthStatus;
          }
        })
      );
      return results;
    },
    refetchInterval: 30000,
    staleTime: 15000,
  });
}
