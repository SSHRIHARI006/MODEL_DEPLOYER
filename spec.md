# Product Specification: Model Marketplace & Universal Compute Platform

This document specifies the technical design, database modifications, API contracts, routing flows, and UI/UX design tokens required to transition the Model Deployer platform from an isolated model hosting environment into a multi-tenant Public Compute Marketplace (inspired by GitHub, Hugging Face, and OpenRouter) utilizing a **decoupled Django REST API backend** and a **React TypeScript frontend**.

---

## 1. Core Architecture & Folder Structure

We decouple the application into two main parts:
1. **Control Plane Backend (Django)**: Located at the project root. Serves pure JSON REST APIs, performs model orchestration, verifies compute credits, handles authentication, and routes inference tasks.
2. **Explore & Registry Frontend (React + TypeScript + Vite)**: Located at `/frontend`. A single-page application (SPA) rendering the high-density console, playground, wallet, and public explorer directory.

### Project Layout:
```
MODEL_DEPLOYER/
├── config/                  # Django project configuration
├── authentication/          # User authentication views (REST APIs)
├── model_registry/          # Model registry and metadata management
├── deployments/             # Deployment state machine and workers
├── prediction_gateway/      # Prediction gateway & billing middleware
├── runners/                 # FastAPI runner worker and bridge runners
├── frontend/                # React Vite Frontend (TypeScript)
│   ├── src/
│   │   ├── components/      # Reusable flat UI components
│   │   ├── pages/           # Explore, Profile, ModelRepo, Wallet, Dashboard
│   │   ├── context/         # Auth & Wallet context providers
│   │   ├── index.css        # Monochromatic design system CSS tokens
│   │   └── App.tsx          # Router and view mappings
│   ├── package.json
│   └── vite.config.ts
├── spec.md                  # Product Specification
└── requirements.txt         # Django server dependencies
```

---

## 2. Database Models (PostgreSQL Schema)

### A. Wallet & Billing Ledger
Tracks credits and provides an audit log of transaction history.

```python
class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    credit_balance = models.DecimalField(max_digits=12, decimal_places=4, default=0.0000)
    lifetime_earned = models.DecimalField(max_digits=12, decimal_places=4, default=0.0000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class LedgerTransaction(models.Model):
    class TransactionType(models.TextChoices):
        INFERENCE = "INFERENCE", "Inference Charge"
        DEPOSIT = "DEPOSIT", "Wallet Credit Deposit"
        PAYOUT = "PAYOUT", "Creator Payout"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consumer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="spent_transactions")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="earned_transactions")
    model = models.ForeignKey('model_registry.Model', on_delete=models.SET_NULL, null=True)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=4)
    creator_share = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    platform_share = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    timestamp = models.DateTimeField(auto_now_add=True)
```

### B. Universal API Keys
Consolidates keys to a user-level association.

```python
class UniversalAPIKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    hashed_key = models.CharField(max_length=128, unique=True)
    prefix = models.CharField(max_length=8)  # md_live_...
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
```

### C. Updated Model Registry Schema
Adds visibility settings, pricing specs, and descriptions.

```python
# Extensions to existing Model model
class Model(models.Model):
    # ... existing fields (name, owner, framework, etc.)
    is_public = models.BooleanField(default=False)
    cost_per_run = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000)
    description = models.TextField(blank=True)  # Short summary
    readme_markdown = models.TextField(blank=True)  # Loaded from model.zip
```

---

## 3. Universal API Routing & Credit Deduction Flow

Inference requests will route through a unified, rate-guarded endpoint.

### Sequence Flow:
1. **Request Submission**:
   - URL: `POST /api/v1/inference/@<username>/<model_name>/`
   - Header: `Authorization: Bearer md_live_<key>`
2. **Authentication & Validation**:
   - Locate user via `UniversalAPIKey` hashing.
   - Fetch target model using `owner__username` and `name`.
   - Ensure the model has a status of `RUNNING`.
3. **Credit Verification**:
   - Check the user's `Wallet.credit_balance`. If balance is less than the model's `cost_per_run`, return `402 Payment Required`.
4. **Compute Proxy**:
   - Forward the inference payload to the model's active FastAPI runner instance.
5. **Deduction & Credit Split**:
   - Deduct `cost_per_run` from the consumer's wallet.
   - Apply an 80/20 credit split:
     - 80% to the Creator's `Wallet.credit_balance` and increment `lifetime_earned`.
     - 20% to the platform fee ledger.
   - Save the immutable `LedgerTransaction`.

---

## 4. REST API Endpoint Specifications

To interface with the React SPA frontend, the Django control plane must expose the following REST APIs:

### Authentication
- `POST /api/auth/register/` (body: `{email, username, password}`) -> `201 Created`
- `POST /api/auth/login/` (body: `{email, password}`) -> `200 OK` (returns JWT `access` and `refresh` tokens)
- `POST /api/auth/refresh/` (body: `{refresh}`) -> `200 OK` (returns new `access` token)

### Explore Directory & Namespaces
- `GET /api/models/explore/` -> `200 OK` (returns paginated lists of public models with filters for framework, owner, search terms)
- `GET /api/users/@<username>/` -> `200 OK` (returns public profile metrics, bio, total inferences served, and list of public models owned)
- `GET /api/models/@<username>/<model_name>/` -> `200 OK` (returns detailed metadata, readme text, deployment status, and per-run pricing)

### Private Dashboard & Management (Requires Auth Token)
- `GET /api/dashboard/summary/` -> `200 OK` (user-specific model count, total invocations, wallet balance)
- `GET /api/keys/` -> `200 OK` (lists user's Universal API keys)
- `POST /api/keys/` -> `201 Created` (creates new Universal API key)
- `DELETE /api/keys/<id>/` -> `204 No Content` (revokes a Universal API key)
- `GET /api/wallet/` -> `200 OK` (returns current balance, earnings, and deposit/transaction history)
- `POST /api/wallet/deposit/` -> `200 OK` (body: `{amount}` -> increases credits for testing)

---

## 5. React Frontend: "GitHub Vibe" Design Tokens & UI/UX

The React interface enforces a strict monochromatic layout with tight padding, sharp borders, and high data density.

### Design Tokens (`frontend/src/index.css`):
- **Base Background**: `#ffffff` (light mode), `#0d1117` (dark mode)
- **Secondary Background**: `#f6f8fa` (light mode), `#161b22` (dark mode)
- **Border style**: `1px solid #d0d7de` (light mode), `1px solid #30363d` (dark mode)
- **Primary Text**: `#24292f` (light mode), `#c9d1d9` (dark mode)
- **Subtle Text**: `#57606a` (light mode), `#8b949e` (dark mode)
- **Subdued Button Action (Green)**: `#2da44e` (light mode), `#238636` (dark mode)
- **Accent Link (Blue)**: `#0969da` (light mode), `#58a6ff` (dark mode)
- **Font Stack**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`

### Front-End Route Mappings:
- `/` -> Explore Page (public directory of models)
- `/login` / `/register` -> Authentication screens
- `/dashboard` -> Creator management console
- `/dashboard/keys` -> Universal API key management dashboard
- `/dashboard/wallet` -> Credit deposits, ledger transactions, and payout views
- `/@<username>` -> User public profiles
- `/@<username>/<model_name>` -> Model detail repository page (incorporates horizontal tabbed interface: README, Playground, Pricing, Settings)

---

## 6. Technical Risk & Mitigation

- **High-Frequency Ledger Writes**: Doing database writes on every inference will lock rows and exhaust PostgreSQL.
  - *Mitigation*: We will execute credit checks inline, but queue the actual transaction log and wallet updates to an asynchronous database pool or Celery queue. Alternatively, store local balances in Redis caches and flush to Postgres in batches.
- **CORS Blockage**: Browser preventing the React frontend from reaching the Django server.
  - *Mitigation*: Enable standard `django-cors-headers` middleware configured specifically to support localhost and production domain configurations.

---
