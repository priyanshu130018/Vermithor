import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { IncidentDetails } from '../pages/IncidentDetails';
import * as incidentApi from '../api/incidents';
import * as rcaApi from '../api/rca';
import * as retrievalApi from '../api/retrieval';
import * as summaryApi from '../api/summaries';

vi.mock('../api/incidents');
vi.mock('../api/rca');
vi.mock('../api/retrieval');
vi.mock('../api/summaries');

describe('IncidentDetails Component', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  it('renders incident header, overview, and timeline correctly', async () => {
    vi.mocked(incidentApi.fetchIncidentByKey).mockResolvedValue({
      id: '1',
      incident_key: 'INC-000001',
      title: 'Database Outage on Booking API',
      description: 'Elevated 500 errors following deployment',
      severity: 'CRITICAL',
      status: 'OPEN',
      service: 'booking-api',
      environment: 'production',
      confidence: 0.89,
      started_at: '2026-08-29T12:00:00Z',
      created_at: '2026-08-29T12:00:00Z',
      updated_at: '2026-08-29T12:00:00Z',
    });

    vi.mocked(rcaApi.fetchRCAReports).mockResolvedValue({
      items: [
        {
          id: '1',
          analysis_key: 'RCA-000001',
          group_key: 'GRP-000001',
          status: 'COMPLETED',
          analysis_version: '1.0',
          primary_root_cause: 'PostgreSQL Connection Pool Exhaustion',
          primary_confidence: 0.89,
          candidates: [],
          causal_chain: [],
          summary: 'DB Pool saturated',
          created_at: '2026-08-29T12:05:00Z',
          updated_at: '2026-08-29T12:05:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
      total_pages: 1,
    });

    vi.mocked(retrievalApi.fetchRAGContext).mockResolvedValue({
      incident_key: 'INC-000001',
      total_results: 1,
      total_characters: 100,
      context_text: '### [LOG:evt-1] Postgres error',
      context: [
        {
          source_type: 'LOG',
          source_id: 'evt-1',
          title: 'DB Connection Error',
          content: 'FATAL: remaining connection slots are reserved',
          final_score: 0.95,
          semantic_score: 0.95,
          metadata_score: 1.0,
          recency_score: 1.0,
          source_weight: 0.8,
          citation: '[LOG:evt-1]',
        },
      ],
      warnings: [],
    });

    vi.mocked(summaryApi.fetchSummariesForIncident).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 1,
      total_pages: 1,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/incidents/INC-000001']}>
          <Routes>
            <Route path="/incidents/:incidentKey" element={<IncidentDetails />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText('INC-000001')).toBeInTheDocument();
    expect(screen.getByText('Database Outage on Booking API')).toBeInTheDocument();
    expect(screen.getByText('PostgreSQL Connection Pool Exhaustion')).toBeInTheDocument();
    expect(screen.getByText('PROBABLE ROOT CAUSE')).toBeInTheDocument();
    expect(screen.getByText('INCIDENT CHRONOLOGICAL TIMELINE')).toBeInTheDocument();
  });
});
