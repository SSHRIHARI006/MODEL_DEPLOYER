"""Deployment-configuration invariants for SEC-01.

These read `docker-compose.yml` and the MinIO policy directly: the runner's
credential isolation is a property of the deployment, and a regression there is
invisible to the application test suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
POLICY_PATH = REPO_ROOT / "deploy" / "minio" / "worker-artifacts-readonly-policy.json"

# The only variables the inference runner may see.
WORKER_ALLOWED_ENV = {
    "STORAGE_ROOT",
    "RUNNER_AUTH_TOKEN",
    "RUNNER_AUTH_HEADER",
    "MINIO_ENDPOINT",
    "MINIO_BUCKET",
    "MINIO_USE_SSL",
    "MINIO_WORKER_USER",
    "MINIO_WORKER_PASSWORD",
}

FORBIDDEN_ENV_PREFIXES = ("DJANGO_", "POSTGRES_", "CELERY_")
FORBIDDEN_ENV_EXACT = {"REDIS_URL", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "AWS_SECRET_ACCESS_KEY"}
INTERNAL_SERVICES = ("db", "redis", "minio", "worker", "celery-worker", "minio-init")


def worker_service() -> dict:
    return COMPOSE["services"]["worker"]


def test_worker_environment_is_an_explicit_allowlist():
    environment = worker_service()["environment"]

    assert set(environment) <= WORKER_ALLOWED_ENV, sorted(
        set(environment) - WORKER_ALLOWED_ENV
    )
    assert {
        "STORAGE_ROOT",
        "RUNNER_AUTH_TOKEN",
        "MINIO_ENDPOINT",
        "MINIO_BUCKET",
        "MINIO_WORKER_USER",
        "MINIO_WORKER_PASSWORD",
    } <= set(environment)


def test_worker_does_not_inherit_the_deployment_env_file():
    assert "env_file" not in worker_service()


def test_worker_has_no_control_plane_credentials():
    offenders = [
        name
        for name in worker_service()["environment"]
        if name.startswith(FORBIDDEN_ENV_PREFIXES) or name in FORBIDDEN_ENV_EXACT
    ]

    assert offenders == []


def test_worker_does_not_receive_minio_admin_credentials_anywhere():
    serialized = yaml.safe_dump(worker_service())

    assert "MINIO_ROOT" not in serialized
    assert "env_file" not in serialized


def test_worker_waits_for_the_storage_bootstrap_job():
    depends_on = worker_service()["depends_on"]

    assert depends_on["minio-init"]["condition"] == "service_completed_successfully"


def test_api_waits_for_the_storage_bootstrap_job():
    depends_on = COMPOSE["services"]["api"]["depends_on"]

    assert depends_on["minio-init"]["condition"] == "service_completed_successfully"


def test_internal_services_publish_no_host_ports():
    for name in INTERNAL_SERVICES:
        assert "ports" not in COMPOSE["services"][name], name


def test_redis_requires_authentication():
    redis = COMPOSE["services"]["redis"]
    command = " ".join(str(part) for part in redis["command"])

    assert "--requirepass" in command
    assert "REDIS_PASSWORD" in command


def test_redis_healthcheck_does_not_echo_the_password_in_its_arguments():
    redis = COMPOSE["services"]["redis"]
    healthcheck = " ".join(str(part) for part in redis["healthcheck"]["test"])

    assert healthcheck == "CMD redis-cli ping"
    assert "REDIS_PASSWORD" not in healthcheck
    # redis-cli reads REDISCLI_AUTH from the environment instead.
    assert "REDISCLI_AUTH" in redis["environment"]


def test_minio_init_creates_a_scoped_read_only_identity():
    init = COMPOSE["services"]["minio-init"]
    command = " ".join(str(init["command"]).split())

    assert "mc admin user add" in command
    assert "mc admin policy attach" in command
    assert "modeldeployer-artifacts-readonly" in command
    assert any(
        "worker-artifacts-readonly-policy.json" in mount for mount in init["volumes"]
    )


def test_minio_init_policy_is_read_only():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    actions = {action for statement in policy["Statement"] for action in statement["Action"]}
    resources = [
        resource for statement in policy["Statement"] for resource in statement["Resource"]
    ]

    assert policy["Version"] == "2012-10-17"
    assert all(statement["Effect"] == "Allow" for statement in policy["Statement"])
    assert actions == {"s3:ListBucket", "s3:GetBucketLocation", "s3:GetObject"}
    assert not actions & {"s3:PutObject", "s3:DeleteObject", "s3:*", "*"}
    assert all(resource.startswith("arn:aws:s3:::") for resource in resources)
    assert "arn:aws:s3:::*" not in resources
    assert all("__ARTIFACTS_BUCKET__" in resource for resource in resources)
