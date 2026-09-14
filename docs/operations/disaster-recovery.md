# Vermithor — Disaster Recovery Strategy

This document outlines the disaster recovery architecture, recovery objectives, and structural limitations of the current **Vermithor** deployment.

---

## 1. Architecture Boundaries & State Classification

| Layer | Component | State Type | High Availability (HA) Status |
| :--- | :--- | :--- | :--- |
| **Edge** | OpenResty API Gateway | Stateless | **HA** (Multi-replica with HPA) |
| **Application** | 8 Backend Microservices | Stateless | **HA** (Multi-replica in `values-prod.yaml`) |
| **Cache / Queue** | Redis | Ephemeral State | **Single Pod** (Recoverable via cache warmup) |
| **Primary Store** | PostgreSQL (`pgvector`) | Persistent State | **Single StatefulSet** (Non-HA in local kind) |

> [!WARNING]
> **Application HA $\neq$ Database HA**: While stateless microservices run multiple replicas across Kubernetes nodes, the primary PostgreSQL instance runs as a single StatefulSet pod backed by a local PVC. True enterprise database HA requires external managed services (AWS Aurora, GCP Cloud SQL, or Patroni/CrunchyData operator).

---

## 2. Recovery Objectives

- **Initial RTO Target**: **30 minutes** (Provision clean namespace, restore PVC snapshot or SQL dump).
- **Initial RPO Target**: **24 hours** (Daily logical dump interval).

---

## 3. Disaster Recovery Scenario: Full Cluster Loss

### Step 1: Re-provision Cluster & Storage Class
```bash
kind create cluster --config deploy/kind/cluster.yaml
```

### Step 2: Restore PostgreSQL Database from Archive
```bash
helm upgrade --install vermithor infrastructure/helm/vermithor -f infrastructure/helm/vermithor/values-dev.yaml
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=postgresql -n vermithor --timeout=120s
cat vermithor_backup_latest.sql | kubectl exec -i -n vermithor postgresql-0 -- psql -U vermithor -d vermithor_db
```

### Step 3: Run Database Migrations
```bash
kubectl create job --from=cronjob/db-migration db-migration-manual -n vermithor
```

### Step 4: Verify System Health
```bash
curl -sf http://localhost:8080/health
```
