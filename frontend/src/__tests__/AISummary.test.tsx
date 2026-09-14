import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AISummary } from '../components/incident/AISummary';
import { IncidentSummary } from '../types/summary';

describe('AISummary Component', () => {
  it('renders prompt button when no summary exists', () => {
    const handleGenerate = vi.fn();
    render(
      <AISummary
        summary={null}
        isLoading={false}
        isGenerating={false}
        onGenerate={handleGenerate}
      />
    );

    expect(screen.getByText('AI INCIDENT SUMMARY')).toBeInTheDocument();
    const btn = screen.getByText('Synthesize AI Summary');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(handleGenerate).toHaveBeenCalledWith(false);
  });

  it('renders executive summary, narrative, and RCA confidence when completed', () => {
    const mockSummary: IncidentSummary = {
      id: '1',
      summary_key: 'SUM-000001',
      incident_key: 'INC-000001',
      status: 'COMPLETED',
      summary_version: '1.0',
      model_provider: 'ollama',
      model_name: 'llama3.2:3b',
      executive_summary: 'Connection pool saturation caused elevated latency on booking-api.',
      what_happened: 'Deployment at 12:00 was followed by DB exhaustion at 12:02.',
      probable_root_cause: 'PostgreSQL Connection Pool Exhaustion',
      impact: {
        services: ['booking-api'],
        severity: 'CRITICAL',
        description: '500 errors',
      },
      timeline: [],
      evidence: [],
      remediation: [],
      confidence: 0.89,
      limitations: ['CPU stayed within threshold.'],
      created_at: '2026-08-29T12:05:00Z',
      updated_at: '2026-08-29T12:05:00Z',
    };

    render(
      <AISummary
        summary={mockSummary}
        isLoading={false}
        isGenerating={false}
        onGenerate={vi.fn()}
      />
    );

    expect(screen.getByText('Executive Summary')).toBeInTheDocument();
    expect(screen.getByText('Connection pool saturation caused elevated latency on booking-api.')).toBeInTheDocument();
    expect(screen.getByText('89%')).toBeInTheDocument();
    expect(screen.getByText('CPU stayed within threshold.')).toBeInTheDocument();
  });
});
