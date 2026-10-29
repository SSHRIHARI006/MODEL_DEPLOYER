# Deployment and Rollback Runbook (OPS-02)

This runbook documents the operational lifecycle for deploying new versions and safely executing rollbacks across the MODEL_DEPLOYER stack.

---

## 1. Production Deployment Procedure

### Step 1: Pre-Deployment Backup
Always generate a verified snapshot before any release or migration:
```bash
./scripts/backup.sh /var/backups/model_deployer/$(date +%Y%m%d_%H%M%S)
```
Verify that `postgres.dump` and `storage.tar.gz` are non-empty.

### Step 2: Code Checkout & Dependencies
```bash
git fetch origin main
git checkout tags/v1.X.X  # or release commit SHA

# Backend dependencies
source .venv/bin/activate
pip install -r requirements.txt -r requirements-worker.txt

# Frontend build
cd frontend && npm install && npm run build && cd ..
```

### Step 3: Database Migrations
```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

### Step 4: Service Reload
- **Gunicorn API Workers:**
  ```bash
  kill -HUP $(cat /var/run/gunicorn.pid)
  ```
- **Celery Runner Workers:**
  ```bash
  systemctl restart model-deployer-worker || docker compose restart worker
  ```

### Step 5: Post-Deployment Smoke Verification
Check readiness and liveness endpoints:
```bash
curl -f http://127.0.0.1:8000/api/metrics/live/
curl -f http://127.0.0.1:8000/api/metrics/ready/
```
Both must return HTTP 200 with all subsystems (`database`, `redis`, `runner`) reported as healthy.

---

## 2. Rollback Procedure

When an unrecoverable regression, failed migration, or critical defect occurs post-deploy:

### Case A: Zero-Schema Rollback (Code Only)
If migrations have not been applied or only backward-compatible columns were added:
1. Check out previous known-good commit:
   ```bash
   git checkout <PREVIOUS_STABLE_SHA>
   ```
2. Rebuild frontend:
   ```bash
   cd frontend && npm run build && cd ..
   ```
3. Reload application services:
   ```bash
   kill -HUP $(cat /var/run/gunicorn.pid)
   systemctl restart model-deployer-worker
   ```
4. Verify with `/api/metrics/ready/`.

### Case B: Migration-Crossing Rollback
If migrations were applied that altered or removed existing schemas:
1. Identify the previous migration target using `showmigrations`:
   ```bash
   python manage.py showmigrations
   ```
2. Target the specific previous migration (e.g., rolling back `billing`):
   ```bash
   python manage.py migrate billing 0002_remove_ledgertransaction_creator_share_and_more
   ```
3. Checkout prior release code:
   ```bash
   git checkout <PREVIOUS_STABLE_SHA>
   ```

### Case C: Catastrophic / Disaster Restore
If data corruption occurred or a migration cannot be reversed cleanly:
1. Stop traffic to API:
   ```bash
   systemctl stop nginx || systemctl stop gunicorn
   ```
2. Execute full database and storage restore from the pre-deployment snapshot:
   ```bash
   ./scripts/restore.sh /var/backups/model_deployer/<snapshot_dir>
   ```
3. Re-run Django system checks:
   ```bash
   python manage.py check
   ```
4. Restart application services and verify readiness endpoints.
