import itertools
from typing import Dict, List, Tuple
from backend.app.common.config import Settings, get_settings
from backend.app.correlation.schemas.correlation import SignalInput
from backend.app.correlation.scoring.factors import (
    evaluate_deployment_proximity,
    evaluate_environment_match,
    evaluate_log_cluster_relationship,
    evaluate_metric_anomaly_relationship,
    evaluate_service_match,
    evaluate_severity_concordance,
    evaluate_time_proximity,
    evaluate_trace_match,
)


class CorrelationScorer:
    """Deterministic, factor-weighted scoring engine for multi-signal correlation."""

    def __init__(self, settings: Settings = None):
        self.settings = settings or get_settings()

    def score_pair(self, s1: SignalInput, s2: SignalInput) -> Tuple[float, List[str]]:
        """
        Evaluate correlation score between two individual signals.

        Returns:
            Tuple[float, List[str]]: Normalized pair score (0.0 to 1.0) and list of explainable reasons.
        """
        reasons: List[str] = []

        # 1. Time proximity
        time_score, time_reason = evaluate_time_proximity(
            s1,
            s2,
            strong_window=self.settings.STRONG_TIME_WINDOW_SECONDS,
            medium_window=self.settings.MEDIUM_TIME_WINDOW_SECONDS,
            max_window=self.settings.CORRELATION_WINDOW_SECONDS,
        )
        if time_reason:
            reasons.append(time_reason)

        # 2. Service match
        service_score, service_reason = evaluate_service_match(s1, s2)
        if service_reason:
            reasons.append(service_reason)

        # 3. Environment match
        env_score, env_reason = evaluate_environment_match(s1, s2)
        if env_reason:
            reasons.append(env_reason)

        # 4. Trace ID match
        trace_score, trace_reason = evaluate_trace_match(s1, s2)
        if trace_reason:
            reasons.append(trace_reason)

        # 5. Severity concordance
        sev_score, sev_reason = evaluate_severity_concordance(s1, s2)
        if sev_reason:
            reasons.append(sev_reason)

        # 6. Metric / Anomaly relationship
        metric_score, metric_reason = evaluate_metric_anomaly_relationship(s1, s2)
        if metric_reason:
            reasons.append(metric_reason)

        # 7. Deployment proximity
        dep_score, dep_reason = evaluate_deployment_proximity(s1, s2)
        if dep_reason:
            reasons.append(dep_reason)

        # 8. Log cluster relationship
        cluster_score, cluster_reason = evaluate_log_cluster_relationship(s1, s2)
        if cluster_reason:
            reasons.append(cluster_reason)

        # Weighted composite score
        weighted_score = (
            time_score * self.settings.WEIGHT_TIME
            + service_score * self.settings.WEIGHT_SERVICE
            + env_score * self.settings.WEIGHT_ENVIRONMENT
            + trace_score * self.settings.WEIGHT_TRACE
            + sev_score * self.settings.WEIGHT_SEVERITY
            + metric_score * self.settings.WEIGHT_METRIC
            + dep_score * self.settings.WEIGHT_DEPLOYMENT
            + cluster_score * 0.10
        )

        # Cross-environment penalty: if environments do not match, suppress correlation heavily
        if env_score == 0.0:
            weighted_score *= 0.20

        # Max window penalty: if signals are outside max window, score drops to near zero
        if time_score == 0.0:
            weighted_score *= 0.10

        normalized_score = min(1.0, max(0.0, weighted_score))
        return round(normalized_score, 4), reasons

    def score_group(
        self,
        signals: List[SignalInput],
    ) -> Tuple[float, bool, List[str], Dict[str, Tuple[float, List[str]]]]:
        """
        Evaluate correlation across an entire group of candidate signals.

        Returns:
            Tuple: (group_score, is_correlated, group_reasons, signal_pair_breakdowns)
        """
        if len(signals) < 2:
            return 0.0, False, ["At least two signals are required for correlation evaluation."], {}

        pair_scores: List[float] = []
        all_reasons: List[str] = []
        signal_breakdowns: Dict[str, Tuple[float, List[str]]] = {s.signal_id: (0.0, []) for s in signals}
        signal_pair_accum: Dict[str, List[float]] = {s.signal_id: [] for s in signals}
        signal_reason_accum: Dict[str, List[str]] = {s.signal_id: [] for s in signals}

        for s1, s2 in itertools.combinations(signals, 2):
            score, reasons = self.score_pair(s1, s2)
            pair_scores.append(score)
            all_reasons.extend(reasons)

            signal_pair_accum[s1.signal_id].append(score)
            signal_pair_accum[s2.signal_id].append(score)

            for r in reasons:
                if r not in signal_reason_accum[s1.signal_id]:
                    signal_reason_accum[s1.signal_id].append(r)
                if r not in signal_reason_accum[s2.signal_id]:
                    signal_reason_accum[s2.signal_id].append(r)

        # Calculate group composite score (average across all pair combinations)
        group_score = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0
        group_score = round(min(1.0, max(0.0, group_score)), 4)
        is_correlated = group_score >= self.settings.CORRELATION_THRESHOLD

        # Deduplicate group reasons while preserving order
        unique_group_reasons = []
        for r in all_reasons:
            if r and r not in unique_group_reasons:
                unique_group_reasons.append(r)

        # Assemble per-signal breakdowns
        for s in signals:
            s_scores = signal_pair_accum[s.signal_id]
            avg_s_score = sum(s_scores) / len(s_scores) if s_scores else group_score
            signal_breakdowns[s.signal_id] = (
                round(avg_s_score, 4),
                signal_reason_accum[s.signal_id],
            )

        return group_score, is_correlated, unique_group_reasons, signal_breakdowns
