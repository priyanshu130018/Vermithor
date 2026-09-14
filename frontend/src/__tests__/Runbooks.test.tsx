import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { Runbooks } from '../pages/Runbooks';
import * as retrievalApi from '../api/retrieval';

vi.mock('../api/retrieval');

describe('Runbooks Page', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  it('renders runbook list and content viewer', async () => {
    vi.mocked(retrievalApi.fetchRunbooks).mockResolvedValue({
      items: [
        {
          id: '1',
          runbook_key: 'RB-000001',
          title: 'PostgreSQL Connection Saturation SOP',
          description: 'SOP for resolving DB exhaustion',
          content: '## Diagnostic Steps\n1. Connect via psql',
          service: 'postgres-db',
          category: 'DATABASE',
          tags: ['postgres', 'db'],
          created_at: '2026-08-29T12:00:00Z',
          updated_at: '2026-08-29T12:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Runbooks />
      </QueryClientProvider>
    );

    expect(screen.getByText('Runbook Knowledge Base')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('RUNBOOK VIEWER')).toBeInTheDocument();
    });
    expect(await screen.findAllByText('RB-000001')).toBeTruthy();
  });
});
