import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { Logs } from '../pages/Logs';
import * as logApi from '../api/logs';

vi.mock('../api/logs');

describe('Logs Page', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  it('renders log search interface and executes query', async () => {
    vi.mocked(logApi.searchLogs).mockResolvedValue({
      query: 'db timeout',
      total_matches: 1,
      matches: [
        {
          id: '1',
          service: 'booking-api',
          severity: 'ERROR',
          normalized_message: 'Connection timed out to host postgres:5432',
          template: 'Connection timed out to host <IP>:<PORT>',
          domain_category: 'DATABASE',
          timestamp: '2026-08-29T12:00:00Z',
          similarity_score: 0.92,
        },
      ],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Logs />
      </QueryClientProvider>
    );

    expect(screen.getByText('Log Intelligence & Vector Search')).toBeInTheDocument();
    const btn = screen.getByText('Vector Search');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);

    expect(await screen.findByText('Connection timed out to host postgres:5432')).toBeInTheDocument();
    expect(screen.getByText('Cosine Sim: 92%')).toBeInTheDocument();
  });
});
