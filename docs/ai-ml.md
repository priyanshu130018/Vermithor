# Vermithor AI/ML Architecture

This document details the machine learning models, statistical detectors, vector embedding pipelines, causal graph analysis algorithms, and Retrieval-Augmented Generation (RAG) LLM synthesis implemented across Vermithor.

---

## 1. Metric Anomaly Detection Pipeline (`anomaly-service`)

Vermithor uses a dual-engine architecture to detect metric irregularities without requiring labeled training datasets:

```text
Raw Metric Observation
         │
         ├──► [ Engine 1: Statistical Z-Score Evaluator ]
         │      Rolling Mean (μ) & Standard Deviation (σ)
         │      Thresholds: Warning at 3.0σ, Critical at 4.0σ
         │
         └──► [ Engine 2: Scikit-Learn Isolation Forest ]
                Unsupervised Tree Partitioning
                Contamination Factor: 'auto'
                Features: Value, Rate of Change (Δv/Δt), Historical Deviation
```

1. **Statistical Detector (`app.detectors.statistical.StatisticalDetector`)**:
   - Calculates rolling mean $\mu$ and standard deviation $\sigma$ across sliding time windows per `(service, metric_name, environment)`.
   - Flags observations exceeding standard deviation cutoffs as `WARNING` ($z \ge 3.0$) or `CRITICAL` ($z \ge 4.0$).
2. **Isolation Forest Detector (`app.detectors.isolation_forest.IsolationForestDetector`)**:
   - Multi-dimensional isolation tree ensemble that isolates anomalies based on path lengths in tree partitions.
   - Outputs continuous anomaly scores mapped to confidence intervals.

---

## 2. Log Intelligence & Dense Vector Embeddings (`log-intelligence-service`)

Unstructured log messages undergo automated preprocessing, sanitization, template extraction, and semantic vector encoding:

```text
Raw Log String: "2026-08-29 12:04:12 ERROR [payment-api] Auth token Bearer eyJhbG... expired for user 4912"
         │
         ▼
[ Step 1: Secret Redaction & Token Normalization ]
Masks JWTs, API keys, UUIDs, IP addresses, IPv6, Timestamps
Result: "ERROR [payment-api] Auth token [REDACTED_JWT] expired for user <NUM>"
         │
         ▼
[ Step 2: Deterministic Log Template Extraction (Drain Heuristics) ]
Extracts invariant schema pattern: "Auth token <TOKEN> expired for user <NUM>"
Template SHA-256 ID: `tpl_8f21a4...`
         │
         ▼
[ Step 3: Domain Categorization Classifier ]
Regex & Keyword Token Matching -> Category: `AUTH` (or `DATABASE`, `NETWORK`, `APPLICATION`)
         │
         ▼
[ Step 4: Dense Vector Embedding Generation ]
Model: `sentence-transformers/all-MiniLM-L6-v2` (PyTorch CPU/GPU inference)
Output: 384-dimensional dense float vector
         │
         ▼
[ Step 5: pgvector Storage & HNSW Indexing ]
Stored in PostgreSQL table `log_entries` with column `embedding vector(384)`
```

---

## 3. Causal Graph Generation & Root Cause Analysis (`rca-service`)

When an incident triggers, correlated signals (anomalies, log alerts, metric spikes) are evaluated to build a directed acyclic graph (DAG) of dependency influences:

1. **Causal Graph Construction (`app.analysis.causal_graph.CausalGraphBuilder`)**:
   - Nodes represent distinct service failure signals.
   - Edges represent causal relationships inferred from:
     - **Temporal Precedence**: Events occurring earlier in the time window precede downstream symptoms.
     - **Service Dependency Topology**: Ingress -> API -> Core Services -> Database.
     - **Error Category Directionality**: Database Connection Timeout $\to$ HTTP 500 Internal Server Error.
2. **Root Cause Candidate Scoring (`app.analysis.scoring.CandidateScorer`)**:
   - Candidates are scored across weighted dimensions:
     - Root topology centrality (lack of parent error causes).
     - Temporal leadership (first anomalous observation in the group).
     - Signal severity and confidence.
   - Produces ranked list of probable root causes with structured confidence scores (e.g., `0.89`).

---

## 4. Grounded RAG & Prompt Construction (`retrieval-service`)

Before invoking the LLM, relevant context is retrieved and formatted with explicit citation identifiers:

```text
Active Incident & RCA Candidates
         │
         ▼
[ Multi-Source Hybrid Search ]
├── Top-K Similar Historical Incidents (pgvector / Metadata matching)
├── Matching Operational Runbooks (Vector similarity search)
└── Correlated High-Severity Logs (Cluster template match)
         │
         ▼
[ Context Assembler & Character Budgeting ]
Formats prompt chunks with strict citation tags:
- `### [INCIDENT:INC-000042] Historical Database Pool Exhaustion`
- `### [RUNBOOK:RBK-PG-POOL] PostgreSQL Connection Pool Scaling Guide`
- `### [LOG:evt-db-91] FATAL: remaining connection slots are reserved for superusers`
Ensures assembled context stays strictly within LLM character bounds (`MAX_PROMPT_CHARS = 30000`).
```

---

## 5. Evidence-Grounded LLM Summary Synthesis (`summary-service`)

1. **Prompt Injection Defense**:
   - Raw user input and log payloads are explicitly delimited in `<UNTRUSTED_TELEMETRY_DATA>` sections with strict system instructions prohibiting directive execution.
2. **Local Model Invocation (`app.llm.ollama_provider.OllamaProvider`)**:
   - Connects to local Ollama server running `llama3.2:3b` via HTTP POST `/api/generate`.
   - Forces structured JSON output schema matching `IncidentSummaryGeneratedSchema`.
3. **Evidence Validation & Citation Guardrails (`app.services.evidence_validator.EvidenceValidator`)**:
   - Cross-references every evidence claim output by the LLM against actual retrieval sources (`valid_source_ids`).
   - Discards ungrounded or hallucinated citations, appending cautionary warnings to the summary's `limitations` block.
4. **Resilience Fallback**:
   - If Ollama is unreachable or times out, the service gracefully degrades to structured fallback synthesis derived from verified RCA candidate data without failing the API response.
