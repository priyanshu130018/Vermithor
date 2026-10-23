import React, { useState, useEffect } from 'react';
import { Shield, CheckSquare, Activity, FileText, RefreshCw } from 'lucide-react';
import {
  PilotReadinessResponse,
  GovernancePolicyResponse,
  IntegrationResponse,
  PilotAuditLogResponse,
  fetchPilotReadiness,
  fetchOnboardingStatus,
  fetchIntegrations,
  fetchPilotAuditLogs,
} from '../api/pilot';
import { OnboardingWizard } from '../components/pilot/OnboardingWizard';
import { ReadinessDashboardView } from '../components/pilot/ReadinessDashboardView';
import { LoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';

export const PilotReadiness: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'wizard' | 'dashboard'>('wizard');
  const [readinessData, setReadinessData] = useState<PilotReadinessResponse | null>(null);
  const [policyData, setPolicyData] = useState<GovernancePolicyResponse | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<PilotAuditLogResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [readiness, policy, ints, logs] = await Promise.all([
        fetchPilotReadiness(),
        fetchOnboardingStatus(),
        fetchIntegrations(),
        fetchPilotAuditLogs(30),
      ]);
      setReadinessData(readiness);
      setPolicyData(policy);
      setIntegrations(ints);
      setAuditLogs(logs);

      // If onboarding is already completed, default to the Dashboard tab
      if (policy.onboarding_completed) {
        setActiveTab('dashboard');
      }
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Failed to load pilot readiness data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (isLoading) {
    return <LoadingState message="Loading pilot operational readiness metrics & governance policies..." />;
  }

  if (errorMsg || !readinessData) {
    return (
      <ErrorState
        title="Pilot Operational Readiness"
        message={errorMsg || 'Could not retrieve pilot status.'}
        onRetry={loadData}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Title & Navigation Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-sky-400" />
            <h1 className="text-xl font-bold text-slate-100 font-mono tracking-wide">
              Customer Pilot Onboarding & Operational Readiness
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Supervised read-only pilot controls, least-privilege telemetry integration, and incident data governance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            className="px-3 py-1.5 rounded border border-border bg-surface-elevated/40 hover:bg-surface-elevated text-slate-300 text-xs font-mono flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh Status
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border gap-6 text-xs font-mono">
        <button
          onClick={() => setActiveTab('wizard')}
          className={`pb-3 font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'wizard'
              ? 'border-b-2 border-sky-400 text-sky-400'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <CheckSquare className="w-4 h-4" />
          Guided Pilot Onboarding ({policyData?.completed_steps.length || 0}/8)
        </button>

        <button
          onClick={() => setActiveTab('dashboard')}
          className={`pb-3 font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'dashboard'
              ? 'border-b-2 border-sky-400 text-sky-400'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          Operational Readiness Scorecard
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'wizard' ? (
        <OnboardingWizard
          policy={policyData}
          integrations={integrations}
          onRefresh={loadData}
        />
      ) : (
        <ReadinessDashboardView
          data={readinessData}
          auditLogs={auditLogs}
          onRefresh={loadData}
        />
      )}
    </div>
  );
};
