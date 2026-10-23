import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PilotReadiness } from '../pages/PilotReadiness';
import * as pilotApi from '../api/pilot';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const mockReadiness: pilotApi.PilotReadinessResponse = {
  org_id: 'org_alpha',
  onboarding_completed: true,
  current_step: 8,
  completed_steps: [
    'CONFIRM_IDENTITY',
    'REVIEW_POLICY',
    'SELECT_TELEMETRY',
    'VALIDATE_CONFIG',
    'CONNECTIVITY_CHECK',
    'SAMPLE_INVESTIGATION',
    'RECORD_FEEDBACK',
    'VIEW_READINESS',
  ],
  integrations: [
    {
      id: 'int-01',
      org_id: 'org_alpha',
      integration_type: 'REPLAY_MODE',
      name: 'Sanitized Replay Fixtures',
      status: 'VERIFIED',
      is_verified: true,
      auth_type: 'NONE',
      telemetry_provenance: 'SANITIZED_REPLAY_FIXTURE',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'int-02',
      org_id: 'org_alpha',
      integration_type: 'PROMETHEUS',
      name: 'VPC Prometheus',
      endpoint_url: 'https://prom.internal:9090',
      status: 'CONFIGURED_UNVERIFIED',
      is_verified: false,
      auth_type: 'BEARER',
      auth_credentials_masked: 'Bearer ***8877',
      telemetry_provenance: 'NOT_VERIFIED',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  last_telemetry_check: {
    integration_type: 'REPLAY_MODE',
    name: 'Sanitized Replay Fixtures',
    status: 'VERIFIED',
    telemetry_provenance: 'SANITIZED_REPLAY_FIXTURE',
  },
  latest_investigation: {
    investigation_key: 'INV-000001',
    incident_key: 'INC-PILOT-201',
    status: 'COMPLETED',
    target_service: 'payment-core',
    leading_hypothesis: 'Database connection pool exhaustion',
    confidence: 0.86,
    latency_ms: 13910.4,
    is_fallback: false,
    telemetry_provenance: 'SANITIZED_REPLAY_FIXTURE',
  },
  evidence_completeness: {
    total_evidence_items: 42,
    citation_validity_rate: 1.0,
    evidence_support_rate: 1.0,
  },
  abstentions_and_unresolved: {
    abstentions_count: 2,
    unresolved_feedback_count: 0,
    total_feedback_count: 10,
  },
  operator_feedback_history: [
    {
      id: 'fb-01',
      investigation_key: 'INV-000001',
      incident_key: 'INC-PILOT-201',
      feedback_status: 'CONFIRMED',
      operator_id: 'sre_pilot@org.com',
      confirmed_root_cause: 'PostgreSQL connection pool exhausted',
      created_at: new Date().toISOString(),
    },
  ],
  rate_limit_and_resilience: {
    rate_limit_enabled: true,
    redis_healthy: true,
    degraded_mode_partitioned: true,
  },
  provenance_breakdown: {
    live_production_incidents_count: 0,
    sanitized_postmortem_replays_count: 10,
    mocked_cases_count: 0,
    live_telemetry_verified: false,
  },
  governance_policy: {
    collection_enabled: true,
    investigations_paused: false,
    allow_external_llm: false,
    redact_sensitive_fields: true,
    retention_days: 30,
    acknowledged_read_only: true,
  },
  blockers: [
    'Customer VPC live telemetry collector is not active (Live telemetry is NOT VERIFIED).',
  ],
  readiness_verdict: 'CONDITIONAL_GO_REPLAY_PILOT',
  readiness_summary: 'Authorized for supervised read-only pilot in Sanitized Replay Mode.',
};

const mockPolicy: pilotApi.GovernancePolicyResponse = {
  id: 'pol-01',
  org_id: 'org_alpha',
  onboarding_completed: true,
  current_onboarding_step: 8,
  completed_steps: mockReadiness.completed_steps,
  collection_enabled: true,
  investigations_paused: false,
  allow_external_llm: false,
  redact_sensitive_fields: true,
  retention_days: 30,
  acknowledged_read_only: true,
  updated_at: new Date().toISOString(),
};

describe('PilotReadiness Component', () => {
  beforeEach(() => {
    vi.spyOn(pilotApi, 'fetchPilotReadiness').mockResolvedValue(mockReadiness);
    vi.spyOn(pilotApi, 'fetchOnboardingStatus').mockResolvedValue(mockPolicy);
    vi.spyOn(pilotApi, 'fetchIntegrations').mockResolvedValue(mockReadiness.integrations);
    vi.spyOn(pilotApi, 'fetchPilotAuditLogs').mockResolvedValue([]);
  });

  it('renders pilot readiness scorecard with accurate verdict and blockers', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <PilotReadiness />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText('Customer Pilot Onboarding & Operational Readiness')
      ).toBeInTheDocument();
    });

    // Verify readiness verdict banner
    expect(screen.getByText('CONDITIONAL_GO_REPLAY_PILOT')).toBeInTheDocument();
    expect(
      screen.getByText('Authorized for supervised read-only pilot in Sanitized Replay Mode.')
    ).toBeInTheDocument();

    // Verify blockers are accurately displayed
    expect(
      screen.getByText(/Customer VPC live telemetry collector is not active/)
    ).toBeInTheDocument();

    // Verify explicit integration states in table
    expect(screen.getByText('Sanitized Replay Fixtures')).toBeInTheDocument();
    expect(screen.getByText('VPC Prometheus')).toBeInTheDocument();
    expect(screen.getByText('CONFIGURED_UNVERIFIED')).toBeInTheDocument();
  });

  it('allows switching to guided onboarding workflow and shows all 8 milestones', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <PilotReadiness />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText('Guided Pilot Onboarding (8/8)')
      ).toBeInTheDocument();
    });

    // Click Guided Onboarding tab
    fireEvent.click(screen.getByText('Guided Pilot Onboarding (8/8)'));

    // Verify step buttons are rendered
    expect(screen.getByText('Step 1')).toBeInTheDocument();
    expect(screen.getByText('Step 2')).toBeInTheDocument();
    expect(screen.getByText('Step 8')).toBeInTheDocument();
  });
});
