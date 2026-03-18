# Model Deployer

Model Deployer is a backend platform for uploading, versioning, and serving machine learning models as API endpoints.

## Overview

This project provides a structured system to manage the lifecycle of machine learning models, including upload, deployment, and inference. It is designed with a modular architecture to support future extensions such as containerized deployment, distributed inference, and monitoring.

## Features

* Upload machine learning model packages
* Version control for models
* Deploy models as API endpoints
* Track prediction logs and usage
* API key-based access control
* Admin panel for internal management

## Tech Stack

* Backend: Django, Django REST Framework
* Database: PostgreSQL
* Language: Python 3.12
* Configuration: YAML

## Project Structure

```
MODEL_DEPLOYER/
│
├── users/                  # Custom user model and authentication
├── api_keys/               # API key management
├── model_registry/         # Model and version management
├── deployments/            # Deployment lifecycle
├── prediction_gateway/     # Inference endpoints
├── monitoring/             # Logs and metrics
├── webapp/                 # Basic frontend and templates
├── core/                   # Shared utilities
│
├── config/                 # Django settings and routing
├── templates/              # HTML templates
├── manage.py
```

## Setup

### 1. Clone the repository

```
git clone <repository-url>
cd MODEL_DEPLOYER
```

### 2. Create virtual environment

```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```
pip install -r requirements.txt
```

or if using uv:

```
uv sync
```

### 4. Configure database

Update database settings in `config/settings.py` or use environment variables.

### 5. Run migrations

```
python manage.py makemigrations
python manage.py migrate
```

### 6. Create superuser

```
python manage.py createsuperuser
```

### 7. Run server

```
python manage.py runserver
```

---

## API Endpoints (Initial)

* `POST /api/models/upload/` — Upload model package
* `POST /api/predict/<model_id>/` — Run inference

---

## Current Status

The project currently includes:

* Database schema and relationships
* Admin panel integration
* Basic API routing and testing
* Initial model upload functionality (in progress)

---

## Future Work

* Model execution and inference engine
* Docker-based deployments
* Authentication and permissions
* Dashboard for model monitoring
* Support for multiple ML frameworks

---

## License

This project is for educational and development purposes.
