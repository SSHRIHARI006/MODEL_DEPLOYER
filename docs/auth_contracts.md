# Prediction Auth Threat Model & Route Contracts (API-03)

This document formalizes the authentication contracts, credential privileges, and threat models for prediction routes in MODEL_DEPLOYER.

---

## 1. Route Comparison & Contracts

| Property | Direct Route (`/api/predict/<model_id>/`) | Universal Route (`/api/v1/inference/@<user>/<model>/`) |
| :--- | :--- | :--- |
| **Path** | `/api/predict/<str:model_id>/` | `/api/v1/inference/@<str:username>/<str:model_name>/` |
| **Authentication** | Two-Factor API Credential: Valid JWT Session **AND** Model-Scoped API Key (`X-API-Key`) | Single Credential: Bearer JWT Session **OR** Universal API Key (`X-API-Key`) |
| **Permission Class** | `[IsAuthenticated, HasValidModelAPIKey]` | `[IsAuthenticated]` via `UniversalOrJWTAuthentication` |
| **Key Scope** | Strictly bound to a specific model ID and owner | Bound to user account; valid across all accessible models |
| **Billing & Credits** | Direct internal pipeline (no consumer billing deduction) | Monetized universal pipeline (up-front reservation, debit & refund) |
| **Primary Use Case** | Dedicated model testing, automated internal workers | Public API clients, marketplace consumers, SaaS integrations |

---

## 2. Threat Model & Security Invariants

### 2.1 Credential Isolation
1. **Model-Scoped Key Boundary:**
   - A model-scoped key issued for `Model A` cannot be used to invoke `Model B`, even if both models are owned by the same user.
   - A model-scoped key issued to `User 1` cannot authenticate requests initiated by `User 2`.
2. **Universal API Key Boundary:**
   - Universal keys are stored as cryptographically secure SHA-256 digests (`api_keys_universalapikey.key_hash`). Plaintext keys are shown only once at generation time.
   - Inactive or revoked universal keys are rejected immediately with 401/403.
   - When a universal key is used for inference, `last_used_at` is updated.

### 2.2 Access Control & Model Visibility
1. **Public vs. Private Access:**
   - **Public Models (`is_public=True`):** Any valid caller (JWT session or active universal key) can invoke the model.
   - **Private Models (`is_public=False`):** Accessible **only** by the model owner. Calls by any other authenticated user return `403 Forbidden`.
   - **Unauthenticated Calls:** Return `401 Unauthorized` before checking model visibility or reading request payloads.

### 2.3 Defense in Depth & Throttling
- All inference endpoints are rate-limited via `ConfigurableScopedRateThrottle` (`predict` scope).
- Payload instances are strictly checked against `validate_prediction_instances` to reject malformed inputs before invoking runners.
