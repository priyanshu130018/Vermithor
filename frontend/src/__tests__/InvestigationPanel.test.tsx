import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InvestigationPanel } from '../components/incident/InvestigationPanel';
import { InvestigationResponse } from '../api/investigations';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('InvestigationPanel Component', () => {
  it('renders empty state with prompt when no investigation exists', () => {
    render(
      <InvestigationPanel
        incidentKey="INC-2026-1042"
        investigation={null}
        isLoading={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('LangGraph AI Incident Investigation')).toBeInTheDocument();
    expect(screen.getByText('No AI Investigation Conducted Yet')).toBeInTheDocument();
    expect(screen.getByText('Start AI Investigation')).toBeInTheDocument();
  });

  it('renders completed investigation with evidence, leading hypothesis, and runbooks', () => {
    const mockInvestigation: InvestigationResponse = {
      id: 'inv-uuid-1234',
      investigation_key: 'INV-2026-0001',
      incident_key: 'INC-2026-1042',
      status: 'COMPLETED',
      target_service: 'payment-api',
      environment: 'production',
      leading_hypothesis: 'Database connection pool exhaustion on payment-api',
      confidence: 0.92,
      is_fallback: false,
      model_provider: 'ollama',
      model_name: 'llama3.2',
      created_at: '2026-10-19T12:00:00Z',
      completed_at: '2026-10-19T12:00:30Z',
      report: {
        investigation_id: 'INV-2026-0001',
        incident_key: 'INC-2026-1042',
        title: 'Payment Gateway Connection Starvation',
        target_service: 'payment-api',
        environment: 'production',
        time_window: { lookback: 30 },
        observed_facts: [
          'PostgreSQL active connections reached 100/100 capacity',
          'Downstream payment checkout p99 latency spiked to 3200ms',
        ],
        inferred_relationships: ['payment-api depends on postgresql-cluster'],
        leading_hypothesis: 'Database connection pool exhaustion on payment-api',
        hypothesis_confidence: 0.92,
        hypotheses_evaluated: [
          {
            hypothesis: 'Database connection pool exhaustion on payment-api',
            candidate_type: 'DATABASE',
            original_score: 0.92,
            calibrated_status: 'CONFIRMED',
            supporting_evidence_ids: ['EV-PROM-01'],
            contradicting_evidence_ids: [],
            reasoning: 'Direct Prometheus metric shows 100% active connection saturation.',
          },
        ],
        alternative_explanations: [],
        confirmed_findings: ['Connection pool saturation confirmed by Prometheus metrics'],
        missing_evidence: [],
        contradictory_evidence: [],
        uncertainty_assessment: 'High confidence based on direct telemetry. Passing tests do not guarantee production stability under load.',
        recommended_diagnostic_steps: [
          {
            action: 'Verify pg_stat_activity query durations',
            target_service: 'payment-api',
            rationale: 'Determine if long-running queries are holding pool connections',
            priority: 'HIGH',
            requires_human_approval: true,
          },
        ],
        runbook_references: [
          {
            runbook_id: 'RB-DB-001',
            title: 'Database Pool Exhaustion Recovery SOP',
            action_summary: 'Steps to inspect connection pools and abort idle transactions',
          },
        ],
        evidence_items: [
          {
            evidence_id: 'EV-PROM-01',
            source_type: 'PROMETHEUS',
            source_id: 'payment_pool_active_connections',
            service: 'payment-api',
            claim: 'Pool connection count reached 100/100',
            data: { value: 100 },
          },
        ],
        model_provider: 'ollama',
        model_name: 'llama3.2',
        is_fallback: false,
      },
    };

    render(
      <InvestigationPanel
        incidentKey="INC-2026-1042"
        investigation={mockInvestigation}
        isLoading={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('INV-2026-0001')).toBeInTheDocument();
    expect(screen.getByText('Investigation Completed')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getAllByText('Database connection pool exhaustion on payment-api').length).toBeGreaterThan(0);
    expect(screen.getByText('PostgreSQL active connections reached 100/100 capacity')).toBeInTheDocument();
    expect(screen.getByText('Database Pool Exhaustion Recovery SOP')).toBeInTheDocument();
    expect(screen.getByText(/Verify pg_stat_activity query durations/i)).toBeInTheDocument();
  });
});
