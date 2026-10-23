import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CodeRepairPanel } from '../components/incident/CodeRepairPanel';
import * as repairsApi from '../api/repairs';

vi.mock('../api/repairs', () => ({
  fetchRepairsForIncident: vi.fn(),
  triggerCodeRepair: vi.fn(),
  submitRepairApproval: vi.fn(),
}));

describe('CodeRepairPanel Component', () => {
  const mockRepair: repairsApi.RepairResponse = {
    id: 'rep-uuid-001',
    repair_key: 'REP-000001',
    investigation_key: 'INV-000001',
    incident_key: 'INC-2026-1042',
    status: 'AWAITING_APPROVAL',
    target_branch: 'main',
    repair_branch: 'repair/inc-2026-1042-rep-000001',
    suspected_defect: 'Database connection pool max_pool_size=10 is saturated under concurrent requests.',
    evidence_citations: ['EV-PROM-01: 100/100 active connections'],
    inspected_files: ['src/config.py'],
    proposed_patch: '--- a/src/config.py\n+++ b/src/config.py\n@@ -1,5 +1,5 @@\n-max_pool_size = 10\n+max_pool_size = 50',
    patch_hash: 'abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
    files_changed: ['src/config.py'],
    test_commands: ['pytest tests/test_payment_pool.py'],
    test_results: {
      status: 'VALIDATED',
      total_tests: 4,
      passed: 4,
      failed: 0,
      skipped: 0,
      commands_run: ['pytest tests/test_payment_pool.py'],
      stdout: '4 passed in 0.15s',
      stderr: '',
      duration_ms: 150.0,
      environment_isolated: true,
    },
    validation_status: 'VALIDATED',
    requires_human_approval: true,
    approval_status: 'PENDING',
    model_provider: 'ollama',
    model_name: 'llama3.2',
    is_fallback: false,
    iteration_count: 1,
    created_at: '2026-10-19T12:01:00Z',
    updated_at: '2026-10-19T12:01:30Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders awaiting review repair with proposed patch, test results, and operational notice', async () => {
    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([mockRepair]);

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    expect(screen.getByText('Sandbox Validated')).toBeInTheDocument();
    expect(screen.getByText('Awaiting Human Approval')).toBeInTheDocument();
    expect(screen.getByText(/max_pool_size = 50/)).toBeInTheDocument();
    expect(screen.getByText(/Tests Run:/)).toBeInTheDocument();
    expect(screen.getByText('4 passed')).toBeInTheDocument();
    expect(screen.getByText('Operational Verification Notice')).toBeInTheDocument();
    expect(screen.getByText(/Local Git Branch staged:/)).toBeInTheDocument();
  });

  it('blocks rejection without a documented reason and shows validation message', async () => {
    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([mockRepair]);

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    const rejectBtn = screen.getByText('Reject Patch');
    fireEvent.click(rejectBtn);

    expect(
      screen.getByText('Rejection requires a documented reason in the notes field before submitting.')
    ).toBeInTheDocument();
    expect(repairsApi.submitRepairApproval).not.toHaveBeenCalled();
  });

  it('submits rejection when review notes are provided', async () => {
    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([mockRepair]);
    vi.mocked(repairsApi.submitRepairApproval).mockResolvedValue({
      ...mockRepair,
      status: 'REJECTED',
      approval_status: 'REJECTED',
      approved_by: 'senior_sre@vermithor.io',
      approval_notes: 'Requires database server max_connections increase first.',
    });

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText(/Enter review notes/i);
    fireEvent.change(textarea, {
      target: { value: 'Requires database server max_connections increase first.' },
    });

    const rejectBtn = screen.getByText('Reject Patch');
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(repairsApi.submitRepairApproval).toHaveBeenCalledWith('REP-000001', {
        action: 'REJECT',
        notes: 'Requires database server max_connections increase first.',
        expected_patch_hash: mockRepair.patch_hash,
      });
    });
  });

  it('submits approval with expected_patch_hash and updates UI', async () => {
    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([mockRepair]);
    vi.mocked(repairsApi.submitRepairApproval).mockResolvedValue({
      ...mockRepair,
      status: 'APPROVED',
      approval_status: 'APPROVED',
      approved_by: 'senior_sre@vermithor.io',
      approval_notes: 'Verified safe for canary staging.',
      approved_at: '2026-10-19T12:05:00Z',
    });

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('Approve Patch');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(repairsApi.submitRepairApproval).toHaveBeenCalledWith('REP-000001', {
        action: 'APPROVE',
        notes: 'Approved by engineer',
        expected_patch_hash: mockRepair.patch_hash,
      });
      expect(screen.getByText(/Approved by:/)).toBeInTheDocument();
    });
  });

  it('displays error banner when server rejects approval due to stale patch hash', async () => {
    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([mockRepair]);
    vi.mocked(repairsApi.submitRepairApproval).mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: 'Stale approval error: reviewed patch hash does not match current patch hash. Patch was altered after review.',
        },
      },
    });

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('Approve Patch');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Stale approval error: reviewed patch hash does not match current patch hash/)
      ).toBeInTheDocument();
    });
  });

  it('displays read-only pilot repository badge, commit SHA, and pilot audit notices', async () => {
    const pilotRepair: repairsApi.RepairResponse = {
      ...mockRepair,
      repository_url: 'vermithor/payment-service',
      base_commit: 'b4a2e8c9d01234567890abcdef1234567890abcd',
      is_read_only_pilot: true,
      pilot_audit_notice: 'No repository changes have been published (Read-Only Pilot Mode)',
    };

    vi.mocked(repairsApi.fetchRepairsForIncident).mockResolvedValue([pilotRepair]);

    render(<CodeRepairPanel incidentKey="INC-2026-1042" investigationKey="INV-000001" />);

    await waitFor(() => {
      expect(screen.getByText('REP-000001')).toBeInTheDocument();
    });

    // Check connected repository display
    expect(screen.getByText('vermithor/payment-service')).toBeInTheDocument();
    expect(screen.getByText('CONNECTED (Read-Only Pilot)')).toBeInTheDocument();
    expect(screen.getByText(/Inspected Commit:/)).toBeInTheDocument();
    expect(screen.getByText(/b4a2e8c9d0/)).toBeInTheDocument();

    // Check pilot audit notices
    expect(
      screen.getByText(/No branches, pull requests, or code modifications are published to GitHub/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Pilot Mode Approval Notice:/)
    ).toBeInTheDocument();

    // Test disconnect action
    const disconnectBtn = screen.getByText('Disconnect');
    fireEvent.click(disconnectBtn);

    expect(screen.getByText('REVOKED (Disconnected)')).toBeInTheDocument();
    expect(
      screen.getByText(/Repository disconnected. Inspection and write operations are revoked./)
    ).toBeInTheDocument();
  });
});

