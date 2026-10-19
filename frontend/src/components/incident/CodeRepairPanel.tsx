import React, { useState, useEffect } from 'react';
import {
  Wrench,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  GitPullRequest,
  ShieldCheck,
  Clock,
  Terminal,
  FileCode,
  ThumbsUp,
  ThumbsDown,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import {
  RepairResponse,
  fetchRepairsForIncident,
  triggerCodeRepair,
  submitRepairApproval,
} from '../../api/repairs';

interface CodeRepairPanelProps {
  incidentKey: string;
  investigationKey?: string;
}

export const CodeRepairPanel: React.FC<CodeRepairPanelProps> = ({
  incidentKey,
  investigationKey,
}) => {
  const [repairs, setRepairs] = useState<RepairResponse[]>([]);
  const [selectedRepair, setSelectedRepair] = useState<RepairResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [approvalNotes, setApprovalNotes] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadRepairs = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const items = await fetchRepairsForIncident(incidentKey);
      setRepairs(items);
      if (items.length > 0) {
        setSelectedRepair(items[0]);
      }
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to load code repairs');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (incidentKey) {
      loadRepairs();
    }
  }, [incidentKey]);

  const handleTriggerRepair = async () => {
    if (!investigationKey && repairs.length === 0) {
      setErrorMsg('No investigation key associated with this incident yet.');
      return;
    }
    const targetInvKey = investigationKey || (repairs[0] ? repairs[0].investigation_key : '');
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const newRep = await triggerCodeRepair({
        investigation_key: targetInvKey,
        repository_url: 'local',
        target_branch: 'main',
        auto_create_pr: true,
      });
      setRepairs([newRep, ...repairs]);
      setSelectedRepair(newRep);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Error triggering repair');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApproval = async (action: 'APPROVE' | 'REJECT') => {
    if (!selectedRepair) return;
    if (action === 'REJECT' && !approvalNotes.trim()) {
      setErrorMsg('Rejection requires a documented reason in the notes field before submitting.');
      return;
    }
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const updated = await submitRepairApproval(selectedRepair.repair_key, {
        action,
        notes: approvalNotes.trim() || (action === 'APPROVE' ? 'Approved by engineer' : 'Rejected by engineer'),
        expected_patch_hash: selectedRepair.patch_hash,
      });
      setSelectedRepair(updated);
      setRepairs(repairs.map((r) => (r.repair_key === updated.repair_key ? updated : r)));
      setApprovalNotes('');
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Approval submission failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getValidationBadge = (status: string) => {
    switch (status) {
      case 'VALIDATED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> Sandbox Validated
          </span>
        );
      case 'VALIDATION_FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" /> Tests Failed in Sandbox
          </span>
        );
      case 'VALIDATION_BLOCKED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" /> Validation Blocked
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-700 text-slate-300">
            <Clock className="w-3.5 h-3.5" /> {status}
          </span>
        );
    }
  };

  const getApprovalBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <ThumbsUp className="w-3.5 h-3.5" /> Approved by Human
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <ThumbsDown className="w-3.5 h-3.5" /> Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
            <ShieldCheck className="w-3.5 h-3.5" /> Awaiting Human Approval
          </span>
        );
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
      {/* Panel Header */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <Wrench className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200">AI Code Repair Agent</h3>
            <p className="text-xs text-slate-400">
              Evidence-grounded minimal patch generation and isolated sandbox validation
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadRepairs}
            disabled={isLoading}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
            title="Refresh repairs"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleTriggerRepair}
            disabled={isSubmitting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white transition-colors disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Repairing...
              </>
            ) : (
              <>
                <Wrench className="w-3.5 h-3.5" /> Propose Repair
              </>
            )}
          </button>
        </div>
      </div>

      {/* Safety Notice Banner */}
      <div className="px-5 py-3 bg-amber-500/5 border-b border-amber-500/10 flex items-center gap-2 text-xs text-amber-300">
        <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0" />
        <span>
          <strong>Non-autonomous Security Boundary:</strong> The repair agent never autonomously merges
          code, commits directly to production, or modifies live infrastructure. All patches require explicit human review.
        </span>
      </div>

      {errorMsg && (
        <div className="px-5 py-3 bg-rose-500/10 border-b border-rose-500/20 text-xs text-rose-400">
          {errorMsg}
        </div>
      )}

      {/* Body Content */}
      <div className="p-5 space-y-6">
        {!selectedRepair ? (
          <div className="text-center py-10 space-y-3">
            <div className="p-3 bg-slate-800/40 rounded-full w-12 h-12 mx-auto flex items-center justify-center text-slate-400">
              <FileCode className="w-6 h-6" />
            </div>
            <div className="text-sm font-medium text-slate-300">No Code Repair Proposals Yet</div>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Click &quot;Propose Repair&quot; to inspect authorized source files for {incidentKey}, generate a minimal patch, and validate it in an isolated sandbox.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Metadata Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-lg bg-slate-950/60 border border-slate-800">
              <div className="space-y-1">
                <div className="text-[11px] font-mono text-slate-500">Repair Key</div>
                <div className="text-sm font-mono font-medium text-slate-200">
                  {selectedRepair.repair_key}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] font-mono text-slate-500">Validation Status</div>
                <div>{getValidationBadge(selectedRepair.validation_status)}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] font-mono text-slate-500">Review State</div>
                <div>{getApprovalBadge(selectedRepair.approval_status)}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] font-mono text-slate-500">Provider & Fallback</div>
                <div className="text-xs font-mono text-slate-300">
                  {selectedRepair.model_provider}{' '}
                  {selectedRepair.is_fallback && (
                    <span className="text-amber-400 text-[10px]">(deterministic fallback)</span>
                  )}
                </div>
              </div>
            </div>

            {/* Suspected Defect & Telemetry Citations */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Suspected Code Defect
              </h4>
              <p className="text-xs text-slate-300 leading-relaxed p-3.5 rounded-lg bg-slate-800/30 border border-slate-800">
                {selectedRepair.suspected_defect || 'Defect analysis pending.'}
              </p>
            </div>

            {/* Evidence Citations */}
            {selectedRepair.evidence_citations && selectedRepair.evidence_citations.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Telemetry Evidence Grounding
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {selectedRepair.evidence_citations.map((cite, i) => (
                    <span
                      key={i}
                      className="inline-block text-[11px] font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60"
                    >
                      {cite}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Proposed Patch Diff Viewer */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Proposed Minimal Patch
                </h4>
                {selectedRepair.patch_hash && (
                  <span className="text-[11px] font-mono text-slate-500">
                    SHA-256: {selectedRepair.patch_hash.substring(0, 16)}...
                  </span>
                )}
              </div>

              {selectedRepair.proposed_patch ? (
                <div className="bg-slate-950 rounded-lg p-3.5 font-mono text-xs overflow-x-auto border border-slate-800 max-h-72">
                  <pre className="space-y-0.5">
                    {selectedRepair.proposed_patch.split('\n').map((line, idx) => {
                      let colorClass = 'text-slate-300';
                      if (line.startsWith('+') && !line.startsWith('+++')) {
                        colorClass = 'text-emerald-400 bg-emerald-950/40 px-1 rounded-sm';
                      } else if (line.startsWith('-') && !line.startsWith('---')) {
                        colorClass = 'text-rose-400 bg-rose-950/40 px-1 rounded-sm';
                      } else if (line.startsWith('@@')) {
                        colorClass = 'text-cyan-400 font-bold';
                      } else if (line.startsWith('---') || line.startsWith('+++')) {
                        colorClass = 'text-slate-500 font-bold';
                      }
                      return (
                        <div key={idx} className={colorClass}>
                          {line}
                        </div>
                      );
                    })}
                  </pre>
                </div>
              ) : (
                <div className="p-4 text-xs text-slate-500 bg-slate-950 rounded-lg border border-slate-800">
                  No patch generated. Status: {selectedRepair.status}
                </div>
              )}
            </div>

            {/* Isolated Test Sandbox Results */}
            {selectedRepair.test_results && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-slate-400" /> Isolated Sandbox Execution
                </h4>
                <div className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-slate-400 font-mono">
                    <span>
                      Tests Run: <strong>{selectedRepair.test_results.total_tests}</strong> (
                      <span className="text-emerald-400">{selectedRepair.test_results.passed} passed</span>,{' '}
                      <span className="text-rose-400">{selectedRepair.test_results.failed} failed</span>)
                    </span>
                    <span>Duration: {selectedRepair.test_results.duration_ms.toFixed(1)}ms</span>
                  </div>
                  {selectedRepair.test_results.commands_run && (
                    <div className="font-mono text-[11px] text-slate-500">
                      Commands: {selectedRepair.test_results.commands_run.join(', ')}
                    </div>
                  )}
                  {selectedRepair.test_results.stdout && (
                    <div className="p-2 rounded bg-slate-900 font-mono text-[11px] text-slate-400 overflow-x-auto max-h-36">
                      <pre>{selectedRepair.test_results.stdout}</pre>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Branch / Pull Request Information */}
            <div className="flex items-center justify-between p-3.5 rounded-lg bg-indigo-500/5 border border-indigo-500/20 text-xs">
              <div className="flex items-center gap-2">
                <GitPullRequest className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                <span className="text-slate-200">
                  {selectedRepair.pull_request_url && !selectedRepair.pull_request_url.includes('mock-repo') ? (
                    <>
                      Remote Draft Pull Request prepared on branch{' '}
                      <code className="text-indigo-300 font-mono">{selectedRepair.repair_branch}</code>
                    </>
                  ) : (
                    <>
                      Local Git Branch staged:{' '}
                      <code className="text-indigo-300 font-mono">{selectedRepair.repair_branch || 'local'}</code>{' '}
                      <span className="text-slate-500 text-[11px]">(Staged locally for human review; no remote PR pushed)</span>
                    </>
                  )}
                </span>
              </div>
              {selectedRepair.pull_request_url && !selectedRepair.pull_request_url.includes('mock-repo') && (
                <a
                  href={selectedRepair.pull_request_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-sky-400 hover:text-sky-300 font-medium underline flex-shrink-0"
                >
                  View GitHub PR
                </a>
              )}
            </div>

            {/* Operational Readiness & Grounding Notice */}
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 space-y-1.5 text-xs text-amber-200">
              <div className="flex items-center gap-2 font-semibold text-amber-300">
                <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                Operational Verification Notice
              </div>
              <p className="text-[11px] text-amber-200/90 leading-relaxed">
                Passing isolated unit tests validates syntax and basic assertions, but does NOT prove operational stability under production load.
                Telemetry indicates downstream query latency spikes and database pool exhaustion that require canary verification.
              </p>
              <div className="text-[10px] text-slate-400 pt-1 border-t border-amber-500/15">
                Human review approval records authorization for staging deployment. It strictly DOES NOT autonomously merge, tag, or deploy to production.
              </div>
            </div>

            {/* Human Review & Approval Action */}
            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
              <h4 className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-sky-400" />
                Human Review Boundary
              </h4>

              {selectedRepair.approval_status === 'APPROVED' ? (
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-1">
                  <div>
                    <strong>Approved by:</strong> {selectedRepair.approved_by || 'Human Engineer'} at{' '}
                    {selectedRepair.approved_at ? new Date(selectedRepair.approved_at).toLocaleString() : 'recently'}
                  </div>
                  {selectedRepair.approval_notes && (
                    <div className="text-slate-400">Notes: {selectedRepair.approval_notes}</div>
                  )}
                </div>
              ) : selectedRepair.approval_status === 'REJECTED' ? (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300 space-y-1">
                  <div>
                    <strong>Rejected by:</strong> {selectedRepair.approved_by || 'Human Engineer'}
                  </div>
                  {selectedRepair.approval_notes && (
                    <div className="text-slate-400">Notes: {selectedRepair.approval_notes}</div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <textarea
                    value={approvalNotes}
                    onChange={(e) => setApprovalNotes(e.target.value)}
                    placeholder="Enter review notes, verification findings, or staging deploy instructions..."
                    rows={2}
                    className="w-full px-3 py-2 text-xs bg-slate-900 border border-slate-700/60 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  />
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => handleApproval('APPROVE')}
                      disabled={isSubmitting}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-50"
                    >
                      <ThumbsUp className="w-3.5 h-3.5" /> Approve Patch
                    </button>
                    <button
                      onClick={() => handleApproval('REJECT')}
                      disabled={isSubmitting}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white transition-colors disabled:opacity-50"
                    >
                      <ThumbsDown className="w-3.5 h-3.5" /> Reject Patch
                    </button>
                    <span className="text-[11px] text-slate-500">
                      Explicit confirmation recorded in audit log.
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
