# Blind Generalization Benchmark Fixtures (v2.0.0)

**Dataset Version:** 2.0.0  
**Frozen Timestamp:** 2026-10-20T19:38:10.934223+00:00  
**Total Cases:** 24  
**Root-Cause Families:** 10  
**Ground-Truth Answer Keys SHA-256:** `6b01fdcf2c459e44477a18d7d1d8054fd738ee96202a3c5552072f8779fedb3e`  

## Ground-Truth Isolation

Ground truth answer keys are stored exclusively in `ground_truth/answer_keys.json`.
Scenario fixtures in `scenarios/*.yaml` contain only raw telemetry (`agent_input`).
The investigation pipeline receives no access to answer keys, expected causes, or prohibited terms.
