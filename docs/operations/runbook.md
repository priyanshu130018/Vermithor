# Vermithor — Operational Runbook & Debugging Guide

A quick reference guide for operating, debugging, and inspecting **Vermithor** in local and staging Kubernetes environments.

---

## 1. Core Cluster Inspection Commands

```bash
# View all pods and status in the vermithor namespace
kubectl get pods -n vermithor -o wide

# Inspect deployment replicas and availability
kubectl get deployments -n vermithor

# Check pod resource consumption (CPU/Memory)
kubectl top pods -n vermithor
```

---

## 2. Service Log Inspection

```bash
# Stream API Gateway logs
kubectl logs -n vermithor -l app.kubernetes.io/component=gateway -f

# Stream Ingestion Service logs
kubectl logs -n vermithor -l app.kubernetes.io/component=ingestion-service -f

# Stream Incident Service logs
kubectl logs -n vermithor -l app.kubernetes.io/component=incident-service -f

# Stream RCA Service logs
kubectl logs -n vermithor -l app.kubernetes.io/component=rca-service -f

# Stream Summary Service logs
kubectl logs -n vermithor -l app.kubernetes.io/component=summary-service -f
```

---

## 3. Troubleshooting Pod Failures

```bash
# Detailed pod diagnostic report
kubectl describe pod <pod-name> -n vermithor

# Review recent cluster events (e.g. OOMKilled, ImagePullBackOff, FailedScheduling)
kubectl get events -n vermithor --sort-by='.metadata.creationTimestamp'

# Execute interactive shell inside pod
kubectl exec -it <pod-name> -n vermithor -- /bin/sh
```

---

## 4. Port-Forwarding Local Tools

```bash
# Forward API Gateway (:8080)
kubectl port-forward svc/gateway 8080:80 -n vermithor

# Forward React Dashboard (:5173)
kubectl port-forward svc/frontend 5173:80 -n vermithor

# Forward Grafana Dashboard (:3000)
kubectl port-forward svc/grafana 3000:3000 -n vermithor

# Forward Jaeger UI (:16686)
kubectl port-forward svc/jaeger 16686:16686 -n vermithor
```
