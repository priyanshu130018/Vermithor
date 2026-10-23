import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Shield,
  ShieldCheck,
  Server,
  Activity,
  ArrowRight,
  ArrowLeft,
  Database,
  RefreshCw,
  Lock,
  ThumbsUp,
  ThumbsDown,
  HelpCircle,
} from 'lucide-react';
import {
  OnboardingStep,
  IntegrationResponse,
  GovernancePolicyResponse,
  submitOnboardingStep,
  configureIntegration,
  verifyIntegration,
  IntegrationType,
} from '../../api/pilot';

interface OnboardingWizardProps {
  policy: GovernancePolicyResponse | null;
  integrations: IntegrationResponse[];
  onRefresh: () => void;
}

export const OnboardingWizard: React.FC<OnboardingWizardProps> = ({
  policy,
  integrations,
  onRefresh,
}) => {
  const [activeStep, setActiveStep] = useState<number>(policy?.current_onboarding_step || 1);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Form states
  const [acknowledgedReadOnly, setAcknowledgedReadOnly] = useState<boolean>(
    policy?.acknowledged_read_only || false
  );
  const [selectedIntegrationType, setSelectedIntegrationType] = useState<IntegrationType>('REPLAY_MODE');
  const [endpointUrl, setEndpointUrl] = useState<string>('http://prometheus:9090');
  const [authType, setAuthType] = useState<string>('NONE');
  const [authCredential, setAuthCredential] = useState<string>('');
  const [sampleIncidentKey, setSampleIncidentKey] = useState<string>('INC-PILOT-201');
  const [operatorNotes, setOperatorNotes] = useState<string>('');

  const completedSteps = policy?.completed_steps || [];

  const handleCompleteStep = async (step: OnboardingStep, ackReadOnly?: boolean) => {
    setIsSubmitting(true);
    setActionMessage(null);
    try {
      await submitOnboardingStep(step, operatorNotes || undefined, ackReadOnly);
      setActionMessage(`Milestone '${step}' completed successfully.`);
      onRefresh();
      if (activeStep < 8) {
        setActiveStep(activeStep + 1);
      }
    } catch (err: any) {
      alert('Failed to complete step: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfigureAndVerify = async () => {
    setIsSubmitting(true);
    setActionMessage(null);
    try {
      const configured = await configureIntegration({
        integration_type: selectedIntegrationType,
        name: `${selectedIntegrationType} Provider`,
        endpoint_url: selectedIntegrationType === 'REPLAY_MODE' ? undefined : endpointUrl,
        auth_type: authType,
        auth_credential: authCredential.trim() || undefined,
        allow_internal_hosts: true,
      });

      const verifyRes = await verifyIntegration(configured.id);
      setActionMessage(`Integration ${verifyRes.name}: ${verifyRes.message}`);
      onRefresh();
    } catch (err: any) {
      alert('Configuration or verification failed: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsSubmitting(false);
    }
  };

  const stepsList: Array<{ step: OnboardingStep; title: string; num: number }> = [
    { num: 1, step: 'CONFIRM_IDENTITY', title: 'Confirm Org & Admin Identity' },
    { num: 2, step: 'REVIEW_POLICY', title: 'Review Read-Only Pilot Scope' },
    { num: 3, step: 'SELECT_TELEMETRY', title: 'Select Telemetry Mode' },
    { num: 4, step: 'VALIDATE_CONFIG', title: 'Validate Provider Endpoint' },
    { num: 5, step: 'CONNECTIVITY_CHECK', title: 'Connectivity & Data Check' },
    { num: 6, step: 'SAMPLE_INVESTIGATION', title: 'Run Sample Investigation' },
    { num: 7, step: 'RECORD_FEEDBACK', title: 'Record Operator Feedback' },
    { num: 8, step: 'VIEW_READINESS', title: 'Pilot Readiness & Blockers' },
  ];

  return (
    <div className="space-y-6">
      {/* Wizard Progress Stepper */}
      <div className="bg-surface border border-border rounded-lg p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
          {stepsList.map((s) => {
            const isCompleted = completedSteps.includes(s.step);
            const isCurrent = activeStep === s.num;
            return (
              <button
                key={s.step}
                onClick={() => setActiveStep(s.num)}
                className={`p-2.5 rounded text-left border transition-all text-xs flex flex-col justify-between ${
                  isCurrent
                    ? 'border-sky-500/50 bg-sky-500/10 text-sky-300'
                    : isCompleted
                    ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300'
                    : 'border-border bg-surface-elevated/40 text-slate-400 hover:text-slate-200'
                }`}
              >
                <div className="flex items-center justify-between font-mono mb-1">
                  <span>Step {s.num}</span>
                  {isCompleted ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  ) : isCurrent ? (
                    <Clock className="w-3.5 h-3.5 text-sky-400 animate-spin" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-slate-600" />
                  )}
                </div>
                <div className="font-medium truncate">{s.title}</div>
              </button>
            );
          })}
        </div>
      </div>

      {actionMessage && (
        <div className="p-3 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Step Content Card */}
      <div className="bg-surface border border-border rounded-lg p-6 space-y-6">
        {activeStep === 1 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <Shield className="w-5 h-5 text-sky-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 1: Confirm Organization Identity & Administrator Authority
              </h2>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Before commencing supervised pilot onboarding, verify your organization tenant identifier and confirm that you possess explicit authorization from your platform leadership.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-surface-elevated/40 border border-border p-4 rounded text-xs font-mono">
              <div>
                <span className="text-slate-500 block">Organization Identifier (Tenant Org):</span>
                <span className="text-sky-400 font-bold">{policy?.org_id || 'vermithor'}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Required Administrative Role:</span>
                <span className="text-emerald-400">admin / sre_lead / lead_engineer</span>
              </div>
            </div>
            <div className="flex justify-end pt-4">
              <button
                disabled={isSubmitting}
                onClick={() => handleCompleteStep('CONFIRM_IDENTITY')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Confirm Identity & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 2 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 2: Review Read-Only Pilot Scope & Data-Handling Policy
              </h2>
            </div>
            <div className="space-y-3 text-xs text-slate-300">
              <div className="p-3 bg-surface-elevated/40 border border-border rounded space-y-2">
                <span className="font-semibold text-slate-100 block">Strict Pilot Boundaries Enforced Server-Side:</span>
                <ul className="list-disc list-inside space-y-1 text-slate-400 font-mono text-[11px]">
                  <li>Strictly Read-Only Git: 0 branch pushes, 0 pull requests, 0 automatic merges.</li>
                  <li>Zero Customer Infrastructure Modification: Vermithor does not alter clusters or services.</li>
                  <li>Automatic Secret Scrubbing: API keys, JWTs, and database credentials are masked before storage.</li>
                  <li>External LLM Egress Disabled by Default: Pilot data stays local unless authorized.</li>
                  <li>30-Day Data Retention Window: Full instant purge available at any time via Governance controls.</li>
                </ul>
              </div>

              <label className="flex items-center gap-3 p-3 bg-sky-500/10 border border-sky-500/30 rounded cursor-pointer">
                <input
                  type="checkbox"
                  checked={acknowledgedReadOnly}
                  onChange={(e) => setAcknowledgedReadOnly(e.target.checked)}
                  className="rounded border-slate-700 text-sky-600 focus:ring-sky-500"
                />
                <span className="text-xs text-slate-200 font-medium">
                  I explicitly acknowledge and accept the strict read-only pilot scope and incident data governance policy.
                </span>
              </label>
            </div>
            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(1)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                disabled={!acknowledgedReadOnly || isSubmitting}
                onClick={() => handleCompleteStep('REVIEW_POLICY', true)}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium text-xs flex items-center gap-2"
              >
                Accept Policy & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 3 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <Database className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 3: Select Telemetry Integration or Replay-Only Mode
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Select how Vermithor will source incident telemetry during this pilot phase:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div
                onClick={() => setSelectedIntegrationType('REPLAY_MODE')}
                className={`p-4 rounded border cursor-pointer transition-all ${
                  selectedIntegrationType === 'REPLAY_MODE'
                    ? 'border-emerald-500 bg-emerald-500/10'
                    : 'border-border bg-surface-elevated/40 hover:border-slate-500'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-slate-100">Sanitized Replay Mode</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-400">Recommended</span>
                </div>
                <p className="text-xs text-slate-400">
                  Zero live external connectivity required. Uses 10 independently verified postmortem replay fixtures. Live telemetry remains labeled NOT VERIFIED.
                </p>
              </div>

              <div
                onClick={() => setSelectedIntegrationType('PROMETHEUS')}
                className={`p-4 rounded border cursor-pointer transition-all ${
                  selectedIntegrationType === 'PROMETHEUS'
                    ? 'border-sky-500 bg-sky-500/10'
                    : 'border-border bg-surface-elevated/40 hover:border-slate-500'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-slate-100">Prometheus Metrics</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-500/20 text-sky-400">Live Read-Only</span>
                </div>
                <p className="text-xs text-slate-400">
                  Queries PromQL HTTP API with read-only permissions for service metrics (request rate, errors, latency).
                </p>
              </div>

              <div
                onClick={() => setSelectedIntegrationType('JAEGER')}
                className={`p-4 rounded border cursor-pointer transition-all ${
                  selectedIntegrationType === 'JAEGER'
                    ? 'border-purple-500 bg-purple-500/10'
                    : 'border-border bg-surface-elevated/40 hover:border-slate-500'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-sm text-slate-100">Jaeger / OpenTelemetry</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 text-purple-400">Live Read-Only</span>
                </div>
                <p className="text-xs text-slate-400">
                  Queries Jaeger Query API for distributed trace graphs, latency bottlenecks, and error spans.
                </p>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(2)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('SELECT_TELEMETRY')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Confirm Mode & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 4 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <Server className="w-5 h-5 text-amber-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 4: Configure & Validate Provider Endpoint (SSRF Protected)
              </h2>
            </div>

            {selectedIntegrationType === 'REPLAY_MODE' ? (
              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300 space-y-2">
                <span className="font-semibold block">Replay-Only Configuration:</span>
                <p>
                  No external URL or network endpoint is required. Vermithor loads sanitized historical postmortem fixtures directly from disk. Secrets are completely absent.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-mono text-slate-400 block mb-1">
                    Telemetry Provider Endpoint URL (HTTPS or approved internal container host):
                  </label>
                  <input
                    type="text"
                    value={endpointUrl}
                    onChange={(e) => setEndpointUrl(e.target.value)}
                    placeholder="https://prometheus.internal:9090"
                    className="w-full px-3 py-2 bg-surface-elevated border border-border rounded text-xs text-slate-200 font-mono"
                  />
                  <span className="text-[10px] text-slate-500 block mt-1">
                    Protection enforced: Cloud metadata IPs (169.254.*) and unauthorized private hosts are strictly rejected.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">Authentication Type:</label>
                    <select
                      value={authType}
                      onChange={(e) => setAuthType(e.target.value)}
                      className="w-full px-3 py-2 bg-surface-elevated border border-border rounded text-xs text-slate-200"
                    >
                      <option value="NONE">None (Internal Unauthenticated)</option>
                      <option value="BEARER">Bearer Token</option>
                      <option value="BASIC">Basic Auth</option>
                      <option value="API_KEY">API Key</option>
                    </select>
                  </div>
                  {authType !== 'NONE' && (
                    <div>
                      <label className="text-xs font-mono text-slate-400 block mb-1">Secret / Token (Masked):</label>
                      <input
                        type="password"
                        value={authCredential}
                        onChange={(e) => setAuthCredential(e.target.value)}
                        placeholder="••••••••••••••••"
                        className="w-full px-3 py-2 bg-surface-elevated border border-border rounded text-xs text-slate-200 font-mono"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(3)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('VALIDATE_CONFIG')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Save Configuration & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 5 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <Activity className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 5: Run Connectivity & Data Validation Probe
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Execute a real probe against the configured integration. An integration is never marked verified solely because configuration exists or a mock test passes.
            </p>

            <div className="space-y-3">
              {integrations.length === 0 ? (
                <div className="p-4 bg-surface-elevated/40 border border-border rounded text-xs text-slate-400">
                  No integration configured yet. Click below to register and verify.
                </div>
              ) : (
                integrations.map((i) => (
                  <div key={i.id} className="p-4 bg-surface-elevated/40 border border-border rounded flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-xs text-slate-200 block">{i.name} ({i.integration_type})</span>
                      <span className="text-[11px] font-mono text-slate-400 block">{i.endpoint_url || 'Local sanitized fixtures'}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        Provenance: <span className="text-sky-400">{i.telemetry_provenance}</span>
                      </span>
                    </div>
                    <div>
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs font-mono ${
                          i.status === 'VERIFIED'
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                            : i.status === 'DEGRADED'
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                            : i.status === 'REVOKED'
                            ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                            : 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {i.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex gap-3">
              <button
                disabled={isSubmitting}
                onClick={handleConfigureAndVerify}
                className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-2"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSubmitting ? 'animate-spin' : ''}`} /> Run Connectivity Probe
              </button>
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(4)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('CONNECTIVITY_CHECK')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Confirm Verification & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 6 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <Activity className="w-5 h-5 text-sky-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 6: Run Sample Incident Investigation in Shadow Mode
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Execute a sample investigation using the verified telemetry source. In pilot mode, investigations run with 0 repair workflows triggered and 0 code writes.
            </p>

            <div className="bg-surface-elevated/40 border border-border p-4 rounded space-y-3">
              <div>
                <label className="text-xs font-mono text-slate-400 block mb-1">Target Sample Incident Key:</label>
                <select
                  value={sampleIncidentKey}
                  onChange={(e) => setSampleIncidentKey(e.target.value)}
                  className="w-full px-3 py-2 bg-surface border border-border rounded text-xs text-slate-200 font-mono"
                >
                  <option value="INC-PILOT-201">INC-PILOT-201 (HikariCP connection pool acquisition timeout)</option>
                  <option value="INC-PILOT-202">INC-PILOT-202 (Okta IdP signing cert expired)</option>
                  <option value="INC-PILOT-203">INC-PILOT-203 (Redis maxmemory eviction storm)</option>
                  <option value="INC-PILOT-207">INC-PILOT-207 (Scheduled nominal backup - Abstention test)</option>
                </select>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(5)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('SAMPLE_INVESTIGATION')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Complete Investigation Step <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 7 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <ThumbsUp className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 7: Review Evidence & Record Operator Feedback
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Review cited evidence IDs and record operator ground-truth determination (CONFIRMED, REJECTED, or UNRESOLVED). The original AI report remains 100% immutable.
            </p>

            <div className="p-4 bg-surface-elevated/40 border border-border rounded space-y-3">
              <span className="text-xs font-mono text-slate-300 block font-semibold">Operator Verification Assessment:</span>
              <textarea
                value={operatorNotes}
                onChange={(e) => setOperatorNotes(e.target.value)}
                placeholder="Enter operator observation notes or verified telemetry IDs (e.g. EV-PROM-1, LOG-0001)..."
                rows={3}
                className="w-full px-3 py-2 bg-surface border border-border rounded text-xs text-slate-200"
              />
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(6)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('RECORD_FEEDBACK')}
                className="px-4 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Record Feedback & Proceed <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {activeStep === 8 && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 border-b border-border pb-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-slate-100 font-mono">
                Step 8: View Pilot Readiness & Unresolved Blockers
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              All onboarding milestones have been evaluated. Review final blockers and operational recommendation in the Readiness Dashboard below.
            </p>

            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300 space-y-2">
              <span className="font-semibold block">Onboarding Completion Status:</span>
              <p>
                Guided pilot workflow completed. Supervised read-only pilot authorized in Sanitized Replay Mode.
              </p>
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setActiveStep(7)}
                className="px-4 py-2 rounded border border-border text-slate-300 hover:bg-surface-elevated text-xs flex items-center gap-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={() => handleCompleteStep('VIEW_READINESS')}
                className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-2"
              >
                Finalize Onboarding <CheckCircle2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
