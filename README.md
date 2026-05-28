# Model Deployer 🚀

**Model Deployer** is a developer-first, SRE-grade platform designed to upload, version, and deploy machine learning models as isolated API endpoints (conceptually similar to a "Vercel for ML models"). It bridges the gap between data science and production engineering by handling dependency isolation, secure telemetry, and instant API generation.

---

## 🌟 Core Features

- **Dynamic Runner Environments**: Automatically creates isolated `uv`-based virtual environments and installs dependencies (`pip`) for each model dynamically.
- **Dual-Layer Security**: Protects endpoints with both User Identity (JWT) and Model-Specific Authorization (API Keys).
- **Vercel-Style Developer Console**: A premium, "Dark Glassmorphism" UI built with vanilla technologies for high-density information display and instant UI responsiveness.
- **Robust State Machine**: Enforces `PENDING → BUILDING → RUNNING` lifecycles on all model deployments.
- **Telemetry & Logging**: Tracks prediction latencies, success rates, and streams live environment build logs back to the frontend.

---

## 🏗️ Architecture

Model Deployer is built with a strictly decoupled architecture:

1. **The Control Plane (Django + PostgreSQL)**
   - Manages state, authentication, model metadata, API keys, and deployment lifecycle.
   - Handles `.zip` payload extraction and validation.
2. **The Execution Environment (FastAPI Runner)**
   - A distinct worker pool executing heavy machine learning inferences without blocking the Control Plane.
   - Triggers isolated `uv` virtualenv builds on command.
3. **The Proxy Layer**
   - Routes incoming inference JSON payloads from clients directly to the isolated FastAPI runner serving that specific model.

---

## 💻 Tech Stack

- **Backend**: Django (REST Framework), Python 3.12, SimpleJWT
- **Runner**: FastAPI, Uvicorn, UV (Virtual environment manager)
- **Database**: PostgreSQL (Production) / SQLite (Local Development)
- **Frontend**: Vanilla CSS (CSS Custom Properties, Glassmorphism design system), Vanilla JS, HTML5

---

## 🚀 Getting Started (Local Development)

### 1. Prerequisites
- Python 3.12+
- `uv` installed (`pip install uv`)

### 2. Setup the Control Plane
```bash
# Clone the repository
git clone https://github.com/SSHRIHARI006/MODEL_DEPLOYER.git
cd MODEL_DEPLOYER

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Run migrations and start the Django server
python manage.py migrate
python manage.py runserver 8000
```

### 3. Setup the Runner Worker
Open a new terminal window:
```bash
source .venv/bin/activate
# Start the FastAPI runner on port 8002
uvicorn runners.worker:app --port 8002 --reload
```

---

## 🔑 How to Deploy a Model

1. **Package your model**: Create a `model.zip` containing:
   - `model.yaml` (Metadata declaring framework and requirements)
   - `requirements.txt` (Pip dependencies)
   - `model.pkl` (Serialized Scikit-Learn weights)
2. **Access the Console**: Navigate to `http://127.0.0.1:8000/`.
3. **Upload & Deploy**: Drag and drop your `.zip` file. Model Deployer will extract the bundle, instruct the runner to construct an isolated environment, and spin up a live API endpoint!

---

## 🛡️ License

This project is licensed under the MIT License.
