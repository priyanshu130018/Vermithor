# Vermithor — Production Incident Response Runbook

Standard 11-step operational runbook for Site Reliability Engineers (SREs) triaging production outages with **Vermithor**.

---

## 1. Triage Workflow

```text
[ 1. Detect Alert ]
        │
        ▼
[ 2. Open Vermithor Dashboard ] (http://vermithor.local)
        │
        ▼
[ 3. Inspect Grafana Golden Signals ] (http://localhost:3000)
        │
        ▼
[ 4. Inspect Distributed Traces ] (http://localhost:16686)
        │
        ▼
[ 5. Review Correlated Incident ]
        │
        ▼
[ 6. Analyze RCA Causal Graph ]
        │
        ▼
[ 7. Review Recent Deployment Events ]
        │
        ▼
[ 8. Retrieve Recommended Runbook ]
        │
        ▼
[ 9. Apply Mitigation / Rollback ]
        │
        ▼
[ 10. Verify Telemetry Normalization ]
        │
        ▼
[ 11. Close Incident & Export AI Summary ]
```

---

## 2. Step-by-Step Instructions

1. **Detect**: Receive PagerDuty / alert manager notification for error rate or latency outlier.
2. **Open Dashboard**: Navigate to `http://localhost:5173/incidents` to review active incidents.
3. **Inspect Grafana**: Check the *Vermithor Overview* dashboard to identify affected services and golden signal trends.
4. **Inspect Jaeger**: Search by `traceparent` or service name to spot downstream timeout bottlenecks.
5. **Review Correlated Incident**: Examine the grouped signals (metrics, logs, deployment markers).
6. **Analyze RCA Causal Graph**: Identify the ranked root cause hypothesis (e.g. database pool exhaustion).
7. **Review Deployments**: Check if a recent rollout coincides with the failure onset timestamp.
8. **Retrieve Runbook**: Review the AI-retrieved runbook steps and historical incident resolutions.
9. **Mitigate**: Execute targeted remediation (e.g. `helm rollback` or resource resizing).
10. **Verify**: Observe metric recovery in Grafana and Vermithor.
11. **Close**: Update incident status to `resolved` and export the generated postmortem.
