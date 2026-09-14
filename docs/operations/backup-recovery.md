# Vermithor — Backup & Recovery Runbook

This document details logical and physical backup and restoration procedures for **Vermithor** stateful stores (PostgreSQL and Redis).

---

## 1. Logical PostgreSQL Backup (`pg_dump`)

### Execute Backup
```bash
# Export active database snapshot to compressed SQL archive
kubectl exec -i -n vermithor postgresql-0 -- pg_dump -U vermithor vermithor_db > vermithor_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore from Backup
```bash
# Restore SQL dump into target database
cat vermithor_backup_20260829.sql | kubectl exec -i -n vermithor postgresql-0 -- psql -U vermithor -d vermithor_db
```

---

## 2. Persistent Volume Claim (PVC) Snapshots

In Kubernetes environments supporting CSI VolumeSnapshots:
```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgresql-pvc-snapshot-20260829
  namespace: vermithor
spec:
  volumeSnapshotClassName: csi-hostpath-snapclass
  source:
    persistentVolumeClaimName: data-postgresql-0
```

---

## 3. Retention & Recovery Targets

> [!NOTE]
> These targets represent initial operational planning goals, not cloud SLA guarantees.

- **RPO (Recovery Point Objective)**: Initial target: **24 hours** (via daily automated logical dumps).
- **RTO (Recovery Time Objective)**: Initial target: **30 minutes** (time to provision fresh PVC and restore dump).
- **Retention Schedule**:
  - Daily snapshots: Retain for 7 days.
  - Weekly snapshots: Retain for 4 weeks.
  - Monthly archives: Retain for 12 months.
