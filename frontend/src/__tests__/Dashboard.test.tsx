import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { Dashboard } from '../pages/Dashboard';
import * as incidentApi from '../api/incidents';
import * as healthHook from '../hooks/useHealth';

vi.mock('../api/incidents');
vi.mock('../hooks/useHealth');

describe('Dashboard Component', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  it('renders stats, table, and active incident metrics', async () => {
    vi.mocked(incidentApi.fetchIncidents).mockResolvedValue({
      items: [
        {
          id: '1',
          incident_key: 'INC-000001',
          title: 'Postgres Connection Saturation',
          severity: 'CRITICAL',
          status: 'OPEN',
          service: 'booking-api',
          environment: 'production',
          confidence: 0.89,
          started_at: '2026-08-29T12:00:00Z',
          created_at: '2026-08-29T12:00:00Z',
          updated_at: '2026-08-29T12:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });

    vi.mocked(healthHook.useServiceHealth).mockReturnValue({
      data: [
        { name: 'Incident Service', url: 'http://localhost:8002', port: 8002, status: 'healthy', latencyMs: 12 },
      ],
      isLoading: false,
    } as any);

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Dashboard />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText('Incident Intelligence Command Center')).toBeInTheDocument();
    expect(await screen.findByText('INC-000001')).toBeInTheDocument();
    expect(screen.getByText('booking-api')).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
  });
});
