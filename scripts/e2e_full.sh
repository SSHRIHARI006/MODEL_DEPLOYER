#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
EMAIL="${EMAIL:-full_user_$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-TestPass123!}"
BUNDLE_NAME="${BUNDLE_NAME:-full_model_bundle.zip}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1"; exit 1; }
}

require_cmd curl
require_cmd python3
require_cmd zip

cd "$(dirname "$0")/.."

register_user() {
  echo "[1/12] Register user: $EMAIL"
  curl -sS -X POST "$BASE_URL/api/auth/register/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null || true
}

login_user() {
  echo "[2/12] Login"
  LOGIN_RESPONSE=$(curl -sS -X POST "$BASE_URL/api/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
  ACCESS_TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')
  REFRESH_TOKEN=$(printf '%s' "$LOGIN_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["refresh"])')
  if [[ -z "$ACCESS_TOKEN" ]]; then
    echo "Login failed: $LOGIN_RESPONSE"
    exit 1
  fi
}

refresh_token() {
  echo "[3/12] Refresh token"
  curl -sS -X POST "$BASE_URL/api/auth/refresh/" \
    -H "Content-Type: application/json" \
    -d "{\"refresh\":\"$REFRESH_TOKEN\"}" >/dev/null
}

build_bundle() {
  echo "[4/12] Build model artifact bundle"
  [[ -f model.pkl ]] || python3 model.py
  zip -j "$BUNDLE_NAME" model.pkl model.py requirements.txt model.yaml >/dev/null
}

upload_model() {
  echo "[5/12] Upload model bundle"
  UPLOAD_RESPONSE=$(curl -sS -X POST "$BASE_URL/api/models/upload/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -F "file=@$BUNDLE_NAME")
  MODEL_ID=$(printf '%s' "$UPLOAD_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["model_id"])')
  MODEL_VERSION_ID=$(printf '%s' "$UPLOAD_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["model_version_id"])')
  if [[ -z "$MODEL_ID" ]]; then
    echo "Upload failed: $UPLOAD_RESPONSE"
    exit 1
  fi
  echo "MODEL_ID=$MODEL_ID"
  echo "MODEL_VERSION_ID=$MODEL_VERSION_ID"
}

create_api_key() {
  echo "[6/12] Create API key"
  KEY_RESPONSE=$(curl -sS -X POST "$BASE_URL/api/keys/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"model_id\":\"$MODEL_ID\",\"name\":\"full-key\"}")
  API_KEY=$(printf '%s' "$KEY_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["key"])')
  KEY_ID=$(printf '%s' "$KEY_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  if [[ -z "$API_KEY" ]]; then
    echo "API key creation failed: $KEY_RESPONSE"
    exit 1
  fi
  echo "API_KEY=${API_KEY:0:12}..."
}

list_api_keys() {
  echo "[7/12] List API keys"
  curl -sS "$BASE_URL/api/keys/" -H "Authorization: Bearer $ACCESS_TOKEN" >/dev/null
}

create_deployment() {
  echo "[8/12] Create deployment"
  DEPLOY_RESPONSE=$(curl -sS -X POST "$BASE_URL/api/deployments/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"model_version_id\":\"$MODEL_VERSION_ID\"}")
  DEPLOY_ID=$(printf '%s' "$DEPLOY_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id",""))')
  if [[ -z "$DEPLOY_ID" ]]; then
    echo "Deployment creation failed: $DEPLOY_RESPONSE"
  else
    echo "DEPLOY_ID=$DEPLOY_ID"
  fi
}

predict() {
  echo "[9/12] Predict"
  PRED_RESPONSE=$(curl -sS -X POST "$BASE_URL/api/predict/$MODEL_ID/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"instances": [{"feature_a": 1.2, "feature_b": 0.5}]}')
  echo "$PRED_RESPONSE"
}

dashboard_metrics() {
  echo "[10/12] Metrics overview"
  curl -sS "$BASE_URL/api/metrics/overview/" -H "Authorization: Bearer $ACCESS_TOKEN" >/dev/null

  echo "[11/12] Dashboard summary"
  curl -sS "$BASE_URL/api/metrics/dashboard/summary/" -H "Authorization: Bearer $ACCESS_TOKEN" >/dev/null
}

health_check() {
  echo "[12/12] Health check"
  curl -sS "$BASE_URL/api/metrics/health/" >/dev/null
}

register_user
login_user
refresh_token
build_bundle
upload_model
create_api_key
list_api_keys
create_deployment
predict
[ -n "${KEY_ID:-}" ] && curl -sS -X POST "$BASE_URL/api/keys/$KEY_ID/deactivate/" -H "Authorization: Bearer $ACCESS_TOKEN" >/dev/null || true

dashboard_metrics
health_check

echo "All checks executed."
