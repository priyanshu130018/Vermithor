import React, { useState, useEffect } from 'react';
import {
  Search,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  FileText,
  Layers,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
  Send,
} from 'lucide-react';
import {
  InvestigationResponse,
  submitInvestigationFeedback,
  fetchInvestigationFeedback,
  FeedbackStatus,
  InvestigationFeedbackResponse,
} from '../../api/investigations';
import { useTriggerInvestigation } from '../../hooks/useInvestigation';
import { formatPercentage } from '../../lib/formatters';

interface InvestigationPanelProps {
  incidentKey: string;
  investigation: InvestigationResponse | null | undefined;
  isLoading: boolean;
  onRefresh?: () => void;
}

export const InvestigationPanel: React.FC<InvestigationPanelProps> = ({
  incidentKey,
  investigation,
  isLoading,
  onRefresh,
}) => {
  const [showAllHypotheses, setShowAllHypotheses] = useState(false);
  const [showEvidenceDetails, setShowEvidenceDetails] = useState(false);
  const [feedbackList, setFeedbackList] = useState<InvestigationFeedbackResponse[]>([]);
  const [selectedStatus, setSelectedStatus] = useState<FeedbackStatus | null>(null);
  const [confirmedRootCause, setConfirmedRootCause] = useState('');
  const [evidenceRef, setEvidenceRef] = useState('');
  const [explanation, setExplanation] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackSuccessMsg, setFeedbackSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (investigation?.investigation_key) {
      fetchInvestigationFeedback(investigation.investigation_key)
        .then((data) => setFeedbackList(data))
        .catch(() => {});
    }
  }, [investigation?.investigation_key]);

  const handleSubmitFeedback = async (status: FeedbackStatus) => {
    if (!investigation?.investigation_key) return;
    setIsSubmittingFeedback(true);
    setFeedbackSuccessMsg(null);
    try {
      const res = await submitInvestigationFeedback(investigation.investigation_key, {
        feedback_status: status,
        confirmed_root_cause: confirmedRootCause.trim() || undefined,
        evidence_reference: evidenceRef.trim() || undefined,
        explanation: explanation.trim() || undefined,
      });
      setFeedbackList((prev) => [res, ...prev]);
      setFeedbackSuccessMsg(`Operator assessment recorded as ${status}. Original investigation preserved.`);
      setSelectedStatus(null);
      setConfirmedRootCause('');
      setEvidenceRef('');
      setExplanation('');
    } catch (err: any) {
      alert('Failed to submit feedback: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const triggerMutation = useTriggerInvestigation(incidentKey);

  const handleRunInvestigation = (forceRefresh: boolean = false) => {
    triggerMutation.mutate({ forceRefresh });
  };

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> Investigation Completed
          </span>
        );
      case 'INVESTIGATING':
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Investigating...
          </span>
        );
      case 'INSUFFICIENT_EVIDENCE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" /> Insufficient Telemetry
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" /> Workflow Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-700 text-slate-300">
            <HelpCircle className="w-3.5 h-3.5" /> Not Investigated
          </span>
        );
    }
  };

  const report = investigation?.report;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg mb-6">
      {/* Header */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Search className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-200">
              LangGraph AI Incident Investigation
            </h3>
            <p className="text-xs text-slate-400">
              Multi-signal telemetry correlation, RCA engine calibration, and runbook retrieval
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
              title="Refresh investigation"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          )}
          <button
            onClick={() => handleRunInvestigation(Boolean(investigation))}
            disabled={triggerMutation.isPending || isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-50"
          >
            {triggerMutation.isPending ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Investigating...
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                {investigation ? 'Re-investigate' : 'Start AI Investigation'}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="p-5 space-y-6">
        {!investigation ? (
          <div className="text-center py-10 space-y-3">
            <div className="p-3 bg-slate-800/40 rounded-full w-12 h-12 mx-auto flex items-center justify-center text-slate-400">
              <Search className="w-6 h-6" />
            </div>
            <div className="text-sm font-medium text-slate-300">No AI Investigation Conducted Yet</div>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Initiate an AI investigation to automatically gather Prometheus metrics, Jaeger traces,
              anomaly clusters, service topologies, and runbooks for {incidentKey}.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Metadata Overview Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-lg bg-slate-950/60 border border-slate-800 font-mono text-xs">
              <div className="space-y-1">
                <div className="text-[11px] text-slate-500">Investigation Key</div>
                <div className="text-sm font-semibold text-sky-400">{investigation.investigation_key}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] text-slate-500">Lifecycle Status</div>
                <div>{getStatusBadge(investigation.status)}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] text-slate-500">Confidence Score</div>
                <div className="flex items-center gap-2">
                  <div className="w-20 bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        investigation.confidence >= 0.75
                          ? 'bg-emerald-500'
                          : investigation.confidence >= 0.5
                          ? 'bg-amber-500'
                          : 'bg-rose-500'
                      }`}
                      style={{ width: `${Math.round(investigation.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-slate-300">{formatPercentage(investigation.confidence)}</span>
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-[11px] text-slate-500">Inference Engine</div>
                <div className="text-slate-300">
                  {investigation.model_provider}
                  {investigation.is_fallback && (
                    <span className="text-amber-400 ml-1.5 text-[10px]">(deterministic fallback)</span>
                  )}
                </div>
              </div>
            </div>

            {/* Leading Root Cause Hypothesis */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-400" /> Leading Root-Cause Hypothesis
              </h4>
              <div className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/60 space-y-2">
                <div className="text-sm font-medium text-slate-200">
                  {investigation.leading_hypothesis || 'Root cause undetermined.'}
                </div>
                {report?.uncertainty_assessment && (
                  <p className="text-xs text-slate-400 leading-relaxed border-t border-slate-800 pt-2">
                    <strong>Uncertainty Assessment:</strong> {report.uncertainty_assessment}
                  </p>
                )}
              </div>
            </div>

            {/* Evaluated Candidate Hypotheses */}
            {report?.hypotheses_evaluated && report.hypotheses_evaluated.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Evaluated Hypotheses ({report.hypotheses_evaluated.length})
                  </h4>
                  <button
                    onClick={() => setShowAllHypotheses(!showAllHypotheses)}
                    className="text-xs text-sky-400 hover:text-sky-300 inline-flex items-center gap-1 font-mono"
                  >
                    {showAllHypotheses ? 'Collapse' : 'View All'}
                    {showAllHypotheses ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                </div>
                <div className="space-y-2">
                  {(showAllHypotheses
                    ? report.hypotheses_evaluated
                    : report.hypotheses_evaluated.slice(0, 2)
                  ).map((hyp, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-300">{hyp.hypothesis}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                            hyp.calibrated_status === 'CONFIRMED'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : hyp.calibrated_status === 'PLAUSIBLE'
                              ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {hyp.calibrated_status} (Score: {(hyp.original_score * 100).toFixed(0)}%)
                        </span>
                      </div>
                      <p className="text-slate-400 text-[11px] leading-relaxed">{hyp.reasoning}</p>
                      <div className="flex items-center gap-4 text-[10px] font-mono text-slate-500">
                        <span>Supporting: {hyp.supporting_evidence_ids.length} signals</span>
                        <span>Contradicting: {hyp.contradicting_evidence_ids.length} signals</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Grounded Observed Facts & Telemetry Evidence */}
            {report?.observed_facts && report.observed_facts.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Grounded Telemetry Observations ({report.observed_facts.length})
                  </h4>
                  <button
                    onClick={() => setShowEvidenceDetails(!showEvidenceDetails)}
                    className="text-xs text-sky-400 hover:text-sky-300 inline-flex items-center gap-1 font-mono"
                  >
                    {showEvidenceDetails ? 'Hide Signals' : 'Show Signal Provenance'}
                    {showEvidenceDetails ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  </button>
                </div>
                <ul className="space-y-1.5">
                  {report.observed_facts.map((fact, i) => (
                    <li
                      key={i}
                      className="p-2.5 rounded bg-slate-950/40 border border-slate-800/80 text-xs text-slate-300 flex items-start gap-2"
                    >
                      <span className="text-sky-400 font-bold shrink-0">•</span>
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>

                {/* Evidence Item Provenance Catalog */}
                {showEvidenceDetails && report.evidence_items && report.evidence_items.length > 0 && (
                  <div className="mt-3 p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-2">
                    <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                      Telemetry Evidence Provenance Catalog
                    </div>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {report.evidence_items.map((item, idx) => (
                        <div
                          key={idx}
                          className="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] font-mono space-y-1"
                        >
                          <div className="flex items-center justify-between text-slate-400">
                            <div className="flex items-center gap-2">
                              <span className="text-sky-400 font-bold">{item.evidence_id}</span>
                              {item.is_verified ? (
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                  Verified
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                  {item.verification_status || 'Unverified'}
                                </span>
                              )}
                            </div>
                            <span className="text-slate-400">{item.source_type}</span>
                            <span className="text-slate-500">{item.service}</span>
                          </div>
                          <div className="text-slate-300">{item.claim}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Runbook SOP References */}
            {report?.runbook_references && report.runbook_references.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-sky-400" /> Retrieved Standard Operating Procedures
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {report.runbook_references.map((rb, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs space-y-1"
                    >
                      <div className="font-semibold text-slate-200">{rb.title || rb.runbook_id}</div>
                      <p className="text-[11px] text-slate-400 line-clamp-2">
                        {rb.description || rb.action_summary || 'Standard operational procedure for service recovery.'}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Diagnostic Steps for SRE Review */}
            {report?.recommended_diagnostic_steps && report.recommended_diagnostic_steps.length > 0 && (
              <div className="p-3.5 rounded-lg bg-indigo-500/5 border border-indigo-500/20 text-xs space-y-2">
                <div className="font-semibold text-indigo-300 flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-indigo-400" /> Recommended SRE Diagnostic Procedures
                </div>
                <div className="space-y-1.5">
                  {report.recommended_diagnostic_steps.map((diag, i) => (
                    <div key={i} className="flex items-start gap-2 text-slate-300 text-[11px]">
                      <span className="text-indigo-400 font-bold shrink-0">{i + 1}.</span>
                      <div>
                        <strong>{diag.action}:</strong> {diag.rationale}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Operator Verification & Shadow-Pilot Feedback Control */}
            <div className="mt-4 p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-sky-400" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                    Operator Verification Assessment
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                  Supervised Shadow Pilot
                </span>
              </div>

              <p className="text-[11px] text-slate-400 leading-relaxed">
                Record independent verification of this AI diagnosis. Operator assessments are recorded separately for evaluation
                and will <strong>not</strong> alter the immutable investigation report or trigger automated code repairs.
              </p>

              {feedbackSuccessMsg && (
                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>{feedbackSuccessMsg}</span>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedStatus('CONFIRMED')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    selectedStatus === 'CONFIRMED'
                      ? 'bg-emerald-600 text-white'
                      : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20'
                  }`}
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                  Confirm Diagnosis
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedStatus('REJECTED')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    selectedStatus === 'REJECTED'
                      ? 'bg-rose-600 text-white'
                      : 'bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20'
                  }`}
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                  Reject Diagnosis
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedStatus('UNRESOLVED')}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    selectedStatus === 'UNRESOLVED'
                      ? 'bg-amber-600 text-white'
                      : 'bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20'
                  }`}
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                  Mark Unresolved
                </button>
              </div>

              {/* Detail Inputs (Conditional on Status Selection) */}
              {selectedStatus && (
                <div className="space-y-2.5 pt-2 border-t border-slate-800">
                  {selectedStatus === 'REJECTED' && (
                    <div>
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">
                        Actual Root Cause (if identified independently)
                      </label>
                      <input
                        type="text"
                        value={confirmedRootCause}
                        onChange={(e) => setConfirmedRootCause(e.target.value)}
                        placeholder="e.g. CoreDNS upstream UDP timeout causing client HTTP 504s"
                        className="w-full px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">
                      Supporting Evidence Reference (optional)
                    </label>
                    <input
                      type="text"
                      value={evidenceRef}
                      onChange={(e) => setEvidenceRef(e.target.value)}
                      placeholder="e.g. LOG-COREDNS-0491 or PR #104"
                      className="w-full px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">
                      Operator Explanation / Verification Notes
                    </label>
                    <textarea
                      value={explanation}
                      onChange={(e) => setExplanation(e.target.value)}
                      rows={2}
                      placeholder="Provide reasoning or note whether the AI diagnosis helped speed up resolution..."
                      className="w-full px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                    />
                  </div>

                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedStatus(null)}
                      className="px-3 py-1 rounded-lg text-xs text-slate-400 hover:text-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={isSubmittingFeedback}
                      onClick={() => handleSubmitFeedback(selectedStatus)}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-50"
                    >
                      <Send className="w-3 h-3" />
                      {isSubmittingFeedback ? 'Recording...' : 'Submit Assessment'}
                    </button>
                  </div>
                </div>
              )}

              {/* Recorded Feedback History */}
              {feedbackList.length > 0 && (
                <div className="pt-2 border-t border-slate-800 space-y-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                    Recorded Operator Feedback History ({feedbackList.length})
                  </div>
                  <div className="space-y-1.5">
                    {feedbackList.map((fb) => (
                      <div
                        key={fb.id}
                        className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] space-y-1"
                      >
                        <div className="flex items-center justify-between text-slate-400">
                          <span className="font-semibold text-slate-300">
                            Operator: <span className="text-slate-200">{fb.operator_id}</span>
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              fb.feedback_status === 'CONFIRMED'
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : fb.feedback_status === 'REJECTED'
                                ? 'bg-rose-500/10 text-rose-400'
                                : 'bg-amber-500/10 text-amber-400'
                            }`}
                          >
                            {fb.feedback_status}
                          </span>
                        </div>
                        {fb.confirmed_root_cause && (
                          <div className="text-slate-300">
                            <strong>Independent Cause:</strong> {fb.confirmed_root_cause}
                          </div>
                        )}
                        {fb.evidence_reference && (
                          <div className="text-slate-400">
                            <strong>Evidence Citation:</strong> {fb.evidence_reference}
                          </div>
                        )}
                        {fb.explanation && (
                          <div className="text-slate-400 italic">"{fb.explanation}"</div>
                        )}
                      </div>
                    ))}
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
