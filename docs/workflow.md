# Vermithor End-to-End Workflow

This document illustrates the end-to-end event flow from initial telemetry ingestion to AI-synthesized incident summaries, as well as the developer deployment lifecycle.

---

## 1. End-to-End Incident Processing Pipeline

```text
1. Telemetry Ingestion
   Application logs, metric observations, and error spikes are submitted via POST /api/v1/events.
   Ingestion Service validates payload schemas and queues Celery jobs over Redis.
         │
         ▼
2. Anomaly Detection
   Anomaly Service processes metric observation streams through Statistical z-score evaluation
   and scikit-learn Isolation Forest detectors, publishing anomaly events.
         │
         ▼
3. Signal Correlation
   Correlation Service groups co-occurring anomalies and log alerts within sliding temporal windows
   (e.g., 300s) into unified Correlation Groups based on topology proximity.
         │
         ▼
4. Incident Creation
   Incident Service materializes a new authoritative Incident record (e.g. INC-000001) in DETECTED state,
   linking all associated telemetry events and creating timeline markers.
         │
         ▼
5. Root Cause Analysis (RCA)
   RCA Service builds a directed acyclic causal graph (DAG) across affected components and scores
   root cause candidates, identifying the primary failure source (e.g. Database Connection Saturation).
         │
         ▼
6. Log Intelligence & Semantic Encoding
   Log Intelligence Service sanitizes unstructured logs, extracts Drain templates, and generates
   384-dimensional vector embeddings with sentence-transformers for pgvector storage.
         │
         ▼
7. Grounded Retrieval / RAG
   Retrieval Service searches historical incidents, matched operational runbooks, and relevant log
   clusters, assembling a token-budgeted prompt context with explicit citation tags ([RUNBOOK:RBK-01]).
         │
         ▼
8. Evidence-Grounded LLM Summary
   Summary Service constructs prompt defense guardrails, calls local Ollama (Llama 3.2), and strictly
   validates output JSON claims against verified retrieval source IDs.
         │
         ▼
9. SRE Operator Review (React Dashboard)
   SRE operators view the incident overview, interactive causal DAG graph, evidence citation list,
   remediation playbook, and natural language summary in the web UI.
```

---

## 2. CI/CD & Deployment Workflow

```text
Developer Commit
      │
      ▼
GitHub Actions CI Pipeline (.github/workflows/ci.yml)
      ├── Backend Pytest Matrix (131 Microservice Unit/Integration Tests)
      ├── Gateway Security & JWT Validation Suite
      ├── Observability & Telemetry Assertion Suite
      ├── Frontend TypeScript Build & Vitest Suite
      └── Helm Chart Linting & Manifest Rendering (.github/workflows/helm.yml)
      │
      ▼ (On Tag / Main Merge)
Docker Image Build & Push (.github/workflows/docker.yml)
      ├── ghcr.io/vermithor/gateway
      ├── ghcr.io/vermithor/frontend
      └── ghcr.io/vermithor/*-service (8 Backend Images)
      │
      ▼
Kubernetes Helm Deployment
      ├── Rollout StatefulSets (PostgreSQL pgvector, Redis)
      ├── Execute Database Migration Job (Alembic)
      ├── Rollout Stateless Deployments (8 Microservices, Gateway, Frontend)
      └── Apply Ingress & NetworkPolicies
```
