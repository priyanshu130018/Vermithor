import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RCAExplanation } from '../components/incident/RCAExplanation';
import { RCAAnalysis } from '../types/rca';

describe('RCAExplanation Component', () => {
  it('renders ranked candidates and directed causal chain', () => {
    const mockRCA: RCAAnalysis = {
      id: '1',
      analysis_key: 'RCA-000001',
      group_key: 'GRP-000001',
      status: 'COMPLETED',
      analysis_version: '1.0',
      primary_root_cause: 'PostgreSQL Connection Pool Exhaustion',
      primary_confidence: 0.94,
      candidates: [
        {
          candidate_name: 'PostgreSQL Connection Pool Exhaustion',
          category: 'DATABASE',
          score: 0.94,
          evidence_signals: ['evt-1'],
          rationale: 'Active pool hit limit.',
        },
        {
          candidate_name: 'Config Drift',
          category: 'CONFIG',
          score: 0.65,
          evidence_signals: ['evt-2'],
          rationale: 'Config change noticed.',
        },
      ],
      causal_chain: [
        { step: 1, service: 'deployment', event_type: 'DEPLOYMENT', description: 'Deploy v2.1' },
        { step: 2, service: 'postgres', event_type: 'ERROR', description: 'Pool saturated' },
      ],
      summary: 'Summary',
      created_at: '2026-08-29T12:00:00Z',
      updated_at: '2026-08-29T12:00:00Z',
    };

    render(<RCAExplanation rca={mockRCA} isLoading={false} />);

    expect(screen.getByText('RANKED ROOT CAUSE CANDIDATES')).toBeInTheDocument();
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('PostgreSQL Connection Pool Exhaustion')).toBeInTheDocument();
    expect(screen.getByText('94%')).toBeInTheDocument();
    expect(screen.getByText('DIRECTED CAUSAL CHAIN')).toBeInTheDocument();
    expect(screen.getByText('Deploy v2.1')).toBeInTheDocument();
    expect(screen.getByText('Pool saturated')).toBeInTheDocument();
  });
});
