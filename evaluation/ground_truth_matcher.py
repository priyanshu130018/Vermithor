"""
Explicit scenario-to-cause mappings and strict ground-truth matching for Vermithor benchmarks.

Replaces permissive keyword-only matching with strict regex patterns and domain-specific
negative controls that prevent cross-category false positives (e.g., redis failures
matching database scenarios, or concrete causes matching ambiguous controls).
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ScenarioGroundTruth:
    scenario_name: str
    expected_root_cause: str
    category: str
    is_ambiguous: bool
    target_service: str
    valid_patterns: Tuple[str, ...]
    disallowed_patterns: Tuple[str, ...]


SCENARIO_GROUND_TRUTH_MAP: Dict[str, ScenarioGroundTruth] = {
    "ambiguous_noise": ScenarioGroundTruth(
        scenario_name="ambiguous_noise",
        expected_root_cause="UNKNOWN",
        category="transient_noise",
        is_ambiguous=True,
        target_service="booking-api",
        valid_patterns=(
            r"\bunknown\b",
            r"\binsufficient\s+evidence\b",
            r"\btransient\s+noise\b",
            r"\bisolated\s+transient\b",
            r"\binconclusive\b",
            r"\bindeterminate\b",
        ),
        disallowed_patterns=(
            r"\bdatabase\b",
            r"\bpostgres\b",
            r"\bredis\b",
            r"\bdeployment\b",
            r"\bmemory\b",
            r"\boom\b",
            r"\bauth\b",
            r"\btraffic\b",
            r"\bpool\b",
            r"\bqueue\b",
        ),
    ),
    "auth_failure": ScenarioGroundTruth(
        scenario_name="auth_failure",
        expected_root_cause="auth_failure",
        category="auth",
        is_ambiguous=False,
        target_service="auth-api",
        valid_patterns=(
            r"\bauth(?:entication)?\s+failure\b",
            r"\bjwt\b",
            r"\btoken\b",
            r"\bsigning\s+key\b",
            r"\bjwks\b",
            r"\b401\b",
            r"\bunauthorized\b",
        ),
        disallowed_patterns=(
            r"\bdatabase\b",
            r"\bpostgres\b",
            r"\bredis\b",
            r"\bdeployment\b",
            r"\boom\b",
            r"\bmemory\s+exhaustion\b",
        ),
    ),
    "bad_deployment": ScenarioGroundTruth(
        scenario_name="bad_deployment",
        expected_root_cause="bad_deployment",
        category="deployment",
        is_ambiguous=False,
        target_service="booking-api",
        valid_patterns=(
            r"\b(?:recent|bad|faulty|failed)\s+deployment\b",
            r"\bdeployment\s+(?:regression|failure|issue|event)\b",
            r"\bv2\.4\.8\b",
            r"\brollout\s+failure\b",
            r"\bbad_deployment\b",
        ),
        disallowed_patterns=(
            r"\bredis\b",
            r"\bauth(?:entication)?\s+failure\b",
            r"\bjwt\b",
            r"\boom\b",
            r"\bmemory\s+exhaustion\b",
        ),
    ),
    "database_saturation": ScenarioGroundTruth(
        scenario_name="database_saturation",
        expected_root_cause="database_saturation",
        category="database",
        is_ambiguous=False,
        target_service="postgres",
        valid_patterns=(
            r"\b(?:database|postgres(?:ql)?)\s+(?:saturation|degradation|exhaustion|timeout)\b",
            r"\b(?:database|postgres(?:ql)?)\s+(?:connection\s+)?pool\b",
            r"\bpool\s+exhaustion\b",
            r"\bdatabase_saturation\b",
        ),
        disallowed_patterns=(
            r"\bredis\b",
            r"\bcache\b",
            r"\bauth(?:entication)?\s+failure\b",
            r"\bjwt\b",
            r"\bdeployment\b",
        ),
    ),
    "memory_exhaustion": ScenarioGroundTruth(
        scenario_name="memory_exhaustion",
        expected_root_cause="memory_exhaustion",
        category="memory",
        is_ambiguous=False,
        target_service="catalog-api",
        valid_patterns=(
            r"\bmemory\s+(?:exhaustion|leak)\b",
            r"\boom\b",
            r"\bout\s+of\s+memory\b",
            r"\bheap\s+exhaustion\b",
            r"\bgc\s+pause\b",
            r"\bmemory_exhaustion\b",
        ),
        disallowed_patterns=(
            r"\bdatabase\b",
            r"\bpostgres\b",
            r"\bredis\b",
            r"\bauth\b",
            r"\bjwt\b",
            r"\bdeployment\b",
        ),
    ),
    "payment_pool_exhaustion": ScenarioGroundTruth(
        scenario_name="payment_pool_exhaustion",
        expected_root_cause="database_saturation",
        category="database",
        is_ambiguous=False,
        target_service="payment-api",
        valid_patterns=(
            r"\b(?:database|postgres(?:ql)?)\s+(?:saturation|degradation|exhaustion)\b",
            r"\b(?:connection\s+)?pool\s+exhaustion\b",
            r"\bhikaricp\b",
            r"\bdatabase\s+degradation\b",
            r"\bdatabase_saturation\b",
        ),
        disallowed_patterns=(
            r"\bredis\b",
            r"\bcache\b",
            r"\bauth(?:entication)?\s+failure\b",
            r"\bjwt\b",
        ),
    ),
    "redis_failure": ScenarioGroundTruth(
        scenario_name="redis_failure",
        expected_root_cause="redis_failure",
        category="cache",
        is_ambiguous=False,
        target_service="cache-service",
        valid_patterns=(
            r"\bredis\s+(?:cache\s+)?failure\b",
            r"\bredis\b",
            r"\bcache\s+(?:failure|outage|miss|timeout|connectivity)\b",
            r"\bredis_failure\b",
        ),
        disallowed_patterns=(
            r"\bpostgres\b",
            r"\bdatabase\s+degradation\b",
            r"\bauth(?:entication)?\s+failure\b",
            r"\bjwt\b",
        ),
    ),
    "traffic_spike": ScenarioGroundTruth(
        scenario_name="traffic_spike",
        expected_root_cause="traffic_spike",
        category="traffic_queue",
        is_ambiguous=False,
        target_service="worker-service",
        valid_patterns=(
            r"\btraffic\s+(?:spike|surge)\b",
            r"\bqueue\s+(?:processing\s+)?backlog\b",
            r"\bworker\s+(?:saturation|backlog|pool\s+exhaustion)\b",
            r"\bload\s+spike\b",
            r"\brequest\s+surge\b",
            r"\btraffic_spike\b",
        ),
        disallowed_patterns=(
            r"\bpostgres\b",
            r"\bdatabase\s+degradation\b",
            r"\bredis\b",
            r"\bauth(?:entication)?\s+failure\b",
            r"\bbad_deployment\b",
        ),
    ),
}


class ScenarioCauseMatcher:
    """Strict ground-truth matching engine for incident root causes."""

    @classmethod
    def get_ground_truth(cls, scenario_name: str) -> Optional[ScenarioGroundTruth]:
        clean_name = scenario_name.replace(".yaml", "").strip()
        return SCENARIO_GROUND_TRUTH_MAP.get(clean_name)

    @classmethod
    def matches(
        cls,
        scenario_name: str,
        prediction: str,
        candidate_type: Optional[str] = None,
    ) -> bool:
        """
        Strictly verifies whether prediction matches the ground truth for the scenario.
        Returns False if prediction is empty, matches any disallowed pattern, or fails valid patterns.
        """
        if not prediction or not isinstance(prediction, str):
            return False

        gt = cls.get_ground_truth(scenario_name)
        if not gt:
            return False

        pred_clean = prediction.strip().lower()

        # 1. Negative control check: Disallowed patterns disqualify immediately
        for bad_pat in gt.disallowed_patterns:
            if re.search(bad_pat, pred_clean, re.IGNORECASE):
                return False

        # 2. Check candidate type if provided
        if candidate_type:
            c_type = candidate_type.upper()
            if gt.category == "database" and c_type not in ("DATABASE", "METRIC", "UNKNOWN"):
                return False
            if gt.category == "deployment" and c_type not in ("DEPLOYMENT", "UNKNOWN"):
                return False
            if gt.category == "cache" and c_type not in ("CACHE", "REDIS", "METRIC", "UNKNOWN"):
                return False
            if gt.category == "memory" and c_type not in ("MEMORY", "METRIC", "UNKNOWN"):
                return False
            if gt.category == "auth" and c_type not in ("AUTH", "LOG", "METRIC", "UNKNOWN"):
                return False
            if gt.category == "traffic_queue" and c_type not in ("WORKER", "QUEUE", "TRAFFIC", "METRIC", "UNKNOWN"):
                return False

        # 3. Positive verification: Must match at least one valid pattern
        for pat in gt.valid_patterns:
            if re.search(pat, pred_clean, re.IGNORECASE):
                return True

        return False

    @classmethod
    def evaluate_ranking(
        cls,
        scenario_name: str,
        candidates: List[str],
    ) -> Tuple[bool, bool, float]:
        """
        Compute Top-1 hit, Top-3 hit, and Reciprocal Rank across ordered candidate predictions.

        Returns:
            Tuple[bool, bool, float]: (is_top1_hit, is_top3_hit, reciprocal_rank)
        """
        if not candidates:
            return False, False, 0.0

        top1_hit = cls.matches(scenario_name, candidates[0])

        top3_matches = [cls.matches(scenario_name, c) for c in candidates[:3]]
        top3_hit = any(top3_matches)

        if top1_hit:
            rr = 1.0
        elif len(top3_matches) > 1 and top3_matches[1]:
            rr = 0.5
        elif len(top3_matches) > 2 and top3_matches[2]:
            rr = 1.0 / 3.0
        else:
            rr = 0.0

        return top1_hit, top3_hit, round(rr, 4)
