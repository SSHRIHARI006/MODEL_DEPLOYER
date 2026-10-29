# Alerting Rules and Operational Runbooks (OBS-03)

This document specifies the operational alert thresholds and runbooks for ModelDeploy (P2 release gate).

## 1. Alerting Rules & Thresholds

| Alert Name | Severity | Condition / Threshold | Window | Action Required |
|---|---|---|---|---|
| **HighInferenceErrorRate** | Critical | Error rate > 5% of total requests | 5m | Inspect runner logs, check container memory, check upstream dependencies |
| **ModelLoadFailure** | High | >= 1 failed model builds or readiness checks | 5m | Verify artifact integrity, review requirements.txt dependency resolution |
| **P95LatencyDegraded** | Warning | p95 compute latency > 500ms on warm models | 10m | Check CPU throttling, concurrent inference volume, or single-flight wait times |
| **StaleBuildingDeployments** | Warning | >= 1 deployment in `BUILDING` state older than 15m | Instant | Run `python manage.py reap_stale_builds --threshold-minutes 15` |
| **HighRunnerMemory** | High | Runner container RAM > 3.5GB (out of 4GB limit) | 3m | LRU cache will auto-evict; if persistent, reduce `RUNNER_MAX_WARM_MODELS` or restart worker |
| **StorageDiskWarning** | Warning | Local / S3 storage disk utilization > 80% | 15m | Run `python manage.py reconcile_orphans` to purge abandoned artifacts |
| **CacheUnavailable** | Warning | Redis ping fails or cache error rate > 0 | 1m | Inspect Redis container health; inference falls back to transparent cache-miss |
| **RunnerUnhealthy** | Critical | `/api/metrics/ready/` returns 503 (`runner: down`) | 1m | Restart runner container via `docker compose restart worker` |

---

## 2. Operator Runbooks

### Runbook: StaleBuildingDeployments
1. **Diagnosis:** Run query or management command:
   ```bash
   python manage.py reap_stale_builds --threshold-minutes 15 --dry-run
   ```
2. **Mitigation:**
   ```bash
   python manage.py reap_stale_builds --threshold-minutes 15
   ```
3. **Prevention:** Check Celery worker logs for SIGKILL or memory termination.

### Runbook: HighRunnerMemory / Warm Model Eviction
1. **Diagnosis:** Check live runner status:
   ```bash
   curl -H "X-Runner-Token: $RUNNER_AUTH_TOKEN" http://127.0.0.1:8001/metrics/live
   ```
2. **Mitigation:**
   - The runner automatically evicts the least recently used (LRU) model when `RUNNER_MAX_WARM_MODELS` is reached.
   - If memory remains constrained, tune `RUNNER_MAX_WARM_MODELS=3` in `.env` and restart worker.
